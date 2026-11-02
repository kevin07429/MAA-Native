// <copyright file="DebugControlService.cs" company="MaaAssistantArknights">
// Part of the MaaWpfGui project, maintained by the MaaAssistantArknights team (Maa Team)
// Copyright (C) 2021-2026 MaaAssistantArknights Contributors
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License v3.0 only as published by
// the Free Software Foundation, either version 3 of the License, or
// any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY
// </copyright>

#nullable enable

using System;
using System.Buffers.Binary;
using System.IO;
using System.IO.Pipes;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Media.Imaging;
using MaaWpfGui.Configuration.Factory;
using MaaWpfGui.Configuration.Single.MaaTask;
using MaaWpfGui.Helper;
using MaaWpfGui.States;
using Serilog;
using Stylet;

namespace MaaWpfGui.Services;

internal static class DebugControlService
{
    private static readonly ILogger _logger = Log.ForContext(typeof(DebugControlService));
    private static readonly CancellationTokenSource _lifetime = new();
    private static readonly string _pipeName = "MAA.Debug." + Environment.ProcessId;
    private static NamedPipeServerStream? _pipe;
    private static Task? _worker;

    internal static void Start()
    {
        _worker ??= Task.Run(RunAsync);
    }

    internal static void Stop()
    {
        _lifetime.Cancel();
        _pipe?.Dispose();
    }

    private static async Task RunAsync()
    {
        string descriptor = Path.Combine(PathsHelper.BaseDir, "cache", "debug-control.json");
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(descriptor)!);
            File.WriteAllText(descriptor, JsonSerializer.Serialize(new { pipe = _pipeName, pid = Environment.ProcessId, protocol = 1 }));
            while (!_lifetime.IsCancellationRequested)
            {
                using var pipe = new NamedPipeServerStream(_pipeName, PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                _pipe = pipe;
                try
                {
                    await pipe.WaitForConnectionAsync(_lifetime.Token).ConfigureAwait(false);
                    using var deadline = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token);
                    deadline.CancelAfter(TimeSpan.FromSeconds(30));
                    byte[] header = new byte[4];
                    await pipe.ReadExactlyAsync(header, deadline.Token).ConfigureAwait(false);
                    uint length = BinaryPrimitives.ReadUInt32LittleEndian(header);
                    if (length == 0 || length > 4096)
                    {
                        throw new IOException("Invalid debug request size");
                    }

                    byte[] input = new byte[length];
                    await pipe.ReadExactlyAsync(input, deadline.Token).ConfigureAwait(false);
                    var request = JsonNode.Parse(input)!.AsObject();
                    object result;
                    bool shutdown = false;
                    try
                    {
                        result = await HandleAsync(request).ConfigureAwait(false);
                        shutdown = request["command"]?.GetValue<string>() == "shutdown";
                    }
                    catch (Exception ex)
                    {
                        result = new { ok = false, error = ex.Message };
                    }

                    byte[] output = JsonSerializer.SerializeToUtf8Bytes(result);
                    BinaryPrimitives.WriteUInt32LittleEndian(header, (uint)output.Length);
                    await pipe.WriteAsync(header, deadline.Token).ConfigureAwait(false);
                    await pipe.WriteAsync(output, deadline.Token).ConfigureAwait(false);
                    await pipe.FlushAsync(deadline.Token).ConfigureAwait(false);
                    if (shutdown)
                    {
                        await Execute.OnUIThreadAsync(() => Application.Current.Shutdown()).ConfigureAwait(false);
                    }
                }
                catch (Exception ex) when (!_lifetime.IsCancellationRequested)
                {
                    _logger.Warning(ex, "Local debug request failed");
                }
            }
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
        }
        catch (ObjectDisposedException) when (_lifetime.IsCancellationRequested)
        {
        }
        catch (Exception ex) when (!_lifetime.IsCancellationRequested)
        {
            _logger.Error(ex, "Local debug control stopped unexpectedly");
        }
        finally
        {
            _pipe = null;
        }
    }

    private static async Task<object> HandleAsync(JsonObject request)
    {
        var proxy = Instances.AsstProxy;
        string command = request["command"]?.GetValue<string>() ?? "status";
        switch (command)
        {
            case "status":
                return new { ok = true, pid = Environment.ProcessId, pipe = _pipeName, ready = RunningState.Instance.Inited, idle = RunningState.Instance.Idle, stopping = RunningState.Instance.Stopping, connected = proxy.Connected, running = proxy.AsstRunning(), pause_state = proxy.TaskPauseState() };
            case "pause":
                return new { ok = proxy.PauseTask(), pause_state = proxy.TaskPauseState() };
            case "monitor":
                string monitorAction = request["action"]?.GetValue<string>() ?? "status";
                if (monitorAction is not ("start" or "stop" or "status"))
                {
                    throw new ArgumentException("Unknown monitor action");
                }
                var toolbox = Instances.ToolboxViewModel;
                if (monitorAction == "start" && proxy.AsstRunning())
                {
                    throw new InvalidOperationException("Stop the current task before starting the debug monitor");
                }
                Task monitorChange = Task.CompletedTask;
                await Execute.OnUIThreadAsync(() => {
                    if ((monitorAction == "start" && !toolbox.Peeping) || (monitorAction == "stop" && toolbox.Peeping))
                    {
                        monitorChange = toolbox.Peep();
                    }
                }).ConfigureAwait(false);
                await monitorChange.ConfigureAwait(false);
                object monitorStatus = new { ok = false };
                await Execute.OnUIThreadAsync(() => {
                    monitorStatus = new { ok = true, active = toolbox.Peeping, width = toolbox.PeepImage?.PixelWidth ?? 0, height = toolbox.PeepImage?.PixelHeight ?? 0, fps = toolbox.PeepScreenFpf };
                }).ConfigureAwait(false);
                return monitorStatus;
            case "resume":
                return new { ok = proxy.ResumeTask(), pause_state = proxy.TaskPauseState() };
            case "connect":
                if (!RunningState.Instance.Idle || proxy.AsstRunning())
                {
                    throw new InvalidOperationException("Stop the current task before connecting");
                }

                return await Task.Run<object>(() => {
                    string error = string.Empty;
                    bool connected = proxy.AsstConnect(ref error);
                    return new { ok = connected, error };
                }).ConfigureAwait(false);
            case "start":
                if (!RunningState.Instance.Idle || proxy.AsstRunning())
                {
                    throw new InvalidOperationException("A task is already running");
                }

                Task start = Task.CompletedTask;
                string? name = request["task"]?.GetValue<string>();
                await Execute.OnUIThreadAsync(() => {
                    if (string.IsNullOrEmpty(name))
                    {
                        start = Instances.TaskQueueViewModel.LinkStart();
                    }
                    else
                    {
                        var tasks = ConfigFactory.CurrentConfig.TaskQueue.Where(task => task.GetType().Name.Equals(name + "Task", StringComparison.OrdinalIgnoreCase)).ToArray();
                        if (tasks.Length == 0)
                        {
                            throw new ArgumentException("Unknown configured task");
                        }

                        if (request["facility"] is JsonArray facilities)
                        {
                            if (tasks.Length != 1 || tasks[0] is not InfrastTask original)
                            {
                                throw new ArgumentException("Facility filter requires one Infrast task");
                            }

                            var selected = facilities.Select(item => item!.GetValue<string>()).ToHashSet(StringComparer.OrdinalIgnoreCase);
                            var copy = JsonSerializer.Deserialize<InfrastTask>(JsonSerializer.Serialize(original))!;
                            if (selected.Count == 0 || selected.Any(item => !copy.RoomList.Any(room => room.Room.ToString().Equals(item, StringComparison.OrdinalIgnoreCase))))
                            {
                                throw new ArgumentException("Unknown facility filter");
                            }

                            copy.RoomList = copy.RoomList.Select(room => room with { IsEnabled = selected.Contains(room.Room.ToString()) }).ToList();
                            copy.IsEnable = true;
                            tasks[0] = copy;
                        }

                        start = Instances.TaskQueueViewModel.LinkStartWithTasks(tasks);
                    }
                }).ConfigureAwait(false);
                await start.ConfigureAwait(false);
                return new { ok = proxy.AsstRunning(), running = proxy.AsstRunning() };
            case "stop":
            case "shutdown":
                if (RunningState.Instance.Idle && !proxy.AsstRunning())
                {
                    await Execute.OnUIThreadAsync(() => RunningState.Instance.SetStopping(false)).ConfigureAwait(false);
                    return new { ok = true, running = false };
                }

                Task<bool>? stop = null;
                await Execute.OnUIThreadAsync(() => { stop = Instances.TaskQueueViewModel.Stop(10000); }).ConfigureAwait(false);
                bool stopped = await stop!.ConfigureAwait(false);
                if (!stopped || proxy.AsstRunning())
                {
                    throw new InvalidOperationException("Task did not stop within the timeout");
                }

                return new { ok = true, running = false };
            case "screenshot":
                var image = await proxy.AsstGetFreshImageAsync().ConfigureAwait(false) ?? throw new IOException("No phone image available");
                var encoder = new PngBitmapEncoder();
                encoder.Frames.Add(BitmapFrame.Create(image));
                using (var stream = new MemoryStream())
                {
                    encoder.Save(stream);
                    return new { ok = true, width = image.PixelWidth, height = image.PixelHeight, coordinate_space = "core_image", png_base64 = Convert.ToBase64String(stream.ToArray()) };
                }

            case "click":
                if (!RunningState.Instance.Idle || proxy.AsstRunning())
                {
                    throw new InvalidOperationException("Stop the task before manual phone clicks");
                }

                int x = request["x"]!.GetValue<int>();
                int y = request["y"]!.GetValue<int>();
                var frame = await proxy.AsstGetFreshImageAsync().ConfigureAwait(false) ?? throw new IOException("No phone image available");
                if (x < 0 || y < 0 || x >= frame.PixelWidth || y >= frame.PixelHeight)
                {
                    throw new ArgumentOutOfRangeException(nameof(request), "Click is outside the phone image");
                }

                return new { ok = proxy.DebugClick(x, y), x, y, coordinate_space = "core_image" };
            default:
                throw new ArgumentException("Unknown debug command");
        }
    }
}
