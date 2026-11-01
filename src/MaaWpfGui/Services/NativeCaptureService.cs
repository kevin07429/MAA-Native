// <copyright file="NativeCaptureService.cs" company="MaaAssistantArknights">
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
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using MaaWpfGui.Helper;
using Serilog;

namespace MaaWpfGui.Services;

internal static class NativeCaptureService
{
    private const int Port = 17654;
    private static readonly ILogger _logger = Log.ForContext(typeof(NativeCaptureService));
    private static readonly SemaphoreSlim _gate = new(1, 1);
    private static readonly CancellationTokenSource _lifetime = new();
    private static Process? _server;
    private static Task? _monitor;
    private static string _adb = string.Empty;
    private static string _serial = string.Empty;
    private static bool _ownsForward;
    private static bool _ready;

    internal static void PrepareResources(string resourceDirectory)
    {
        // Reapply local behavior after resource-only updates, without changing upstream assets.
        string path = Path.Combine(resourceDirectory, "config.json");
        var config = JsonNode.Parse(File.ReadAllText(path))!.AsObject();
        config["options"]!["nativeResolution"] = true;
        config["options"]!["taskDelay"] = 200;
        foreach (var entry in config["connection"]!.AsArray())
        {
            if (entry?["configName"]?.GetValue<string>() is not ("General" or "Compatible"))
            {
                continue;
            }

            entry["screencapEncode"] = "[Adb] -s [AdbSerial] exec-out screencap -p";
            entry["extras"] ??= new JsonObject();
            entry["extras"]!["nativeCapturePort"] = 0;
            entry["extras"]!["preferEncodedScreencap"] = false;
        }

        string temporary = path + ".native.tmp";
        File.WriteAllText(temporary, config.ToJsonString());
        File.Move(temporary, path, true);

        string commonPath = Path.Combine(resourceDirectory, "tasks", "tasks.json");
        var common = JsonNode.Parse(File.ReadAllText(commonPath))!.AsObject();
        const string leaveConfirm = "NativeInfrastLeaveConfirm";
        common[leaveConfirm] = new JsonObject {
            ["baseTask"] = "ReturnConfirm",
            ["algorithm"] = "OcrDetect",
            ["text"] = new JsonArray("确认离开罗德岛基建"),
            ["roi"] = new JsonArray(280, 260, 720, 120),
            ["action"] = "ClickRect",
            ["specificRect"] = new JsonArray(850, 465, 130, 60),
            ["screenAnchor"] = "center",
            ["postDelay"] = 500,
            ["next"] = new JsonArray("#back"),
        };
        var returns = common["ReturnButtons"]!["next"]!.AsArray();
        foreach (string entry in new[] { "Infrast", "Recruit", "Mall", "Award", "Fight" })
        {
            if (!common.ContainsKey(entry + "Begin"))
            {
                continue;
            }

            string loading = entry + "@NativeInfrastExitLoading";
            common[loading] = new JsonObject {
                ["baseTask"] = "LoadingIcon",
                ["template"] = "LoadingIcon.png",
                ["roi"] = new JsonArray(360, 130, 560, 450),
                ["postDelay"] = 250,
                ["maxTimes"] = 120,
                ["next"] = new JsonArray("#self", entry + "Begin#next"),
            };
            common[entry + "@" + leaveConfirm] = new JsonObject {
                ["baseTask"] = leaveConfirm,
                ["next"] = new JsonArray(loading, entry + "Begin#next"),
            };
        }

        if (!returns.Any(item => item?.GetValue<string>() == leaveConfirm))
        {
            returns.Insert(0, JsonValue.Create(leaveConfirm));
        }

        // Stay inside the base when moving between rooms. The quick-switch
        // base button is a no-op here and must not precede the room back button.
        common["NativeInfrastOverview"] = new JsonObject {
            ["algorithm"] = "OcrDetect",
            ["text"] = new JsonArray("进驻总览"),
            ["roi"] = new JsonArray(0, 65, 240, 110),
            ["next"] = new JsonArray("InfrastNotification", "Stop"),
        };
        foreach (var facility in new[] { ("Control", "控制中枢"), ("Reception", "会客室"), ("Office", "办公室"), ("Training", "训练室") })
        {
            common["NativeInfrastFacility" + facility.Item1] = new JsonObject {
                ["algorithm"] = "OcrDetect",
                ["text"] = new JsonArray(facility.Item2),
                ["roi"] = new JsonArray(240, 60, 1040, 600),
            };
        }
        common["InfrastBegin"]!["next"] = new JsonArray(
            "Infrast@NativeInfrastLeaveConfirm", "NativeInfrastOverview",
            "Infrast", "InfrastNotification", "InfrastEnteredFlag", "InfrastBegin@InfrastLoading",
            "Infrast@ReturnButton", "Infrast@FromStageSN", "Infrast@FromAnnihilation",
            "Infrast@CloseAnnos#next", "Infrast@OfflineConfirm");
        common["Infrast@" + leaveConfirm]!["specificRect"] = new JsonArray(310, 465, 130, 60);
        common["Infrast@" + leaveConfirm]!["next"] = new JsonArray("InfrastBegin#next");
        common["Infrast@ReturnButton"] = new JsonObject {
            ["baseTask"] = "ReturnButton",
            ["template"] = "Return.png",
            ["postDelay"] = 800,
            ["next"] = new JsonArray("InfrastBegin#next"),
        };

        string commonTemporary = commonPath + ".native.tmp";
        File.WriteAllText(commonTemporary, common.ToJsonString());
        File.Move(commonTemporary, commonPath, true);

        string roguePath = Path.Combine(resourceDirectory, "tasks", "Roguelike", "base.json");
        if (File.Exists(roguePath))
        {
            var tasks = JsonNode.Parse(File.ReadAllText(roguePath))!.AsObject();
            var templates = new JsonArray();
            string themeDirectory = Path.Combine(resourceDirectory, "template", "UiTheme");
            var availableTemplates = Directory.EnumerateFiles(themeDirectory, "Terminal*.png", SearchOption.AllDirectories)
                .Concat(Directory.EnumerateFiles(themeDirectory, "SwitchTheme@ToggleSettingsMenu*.png", SearchOption.AllDirectories))
                .OrderBy(path => path, StringComparer.Ordinal);
            foreach (string template in availableTemplates)
            {
                string relative = Path.GetRelativePath(themeDirectory, template).Replace('\\', '/');
                templates.Add(relative);
            }

            tasks["Roguelike"]!["template"] = templates;
            tasks["Roguelike"]!["roi"] = new JsonArray(800, 50, 480, 300);
            tasks["Roguelike"]!["maskRange"] = new JsonArray(1, 255);
            var next = tasks["Roguelike@Begin"]!["next"]!.AsArray();
            if (!next.Any(entry => entry?.GetValue<string>() == "Roguelike"))
            {
                next.Insert(0, JsonValue.Create("Roguelike"));
            }

            foreach (string theme in new[] { "JieGarden", "Sarkaz", "Phantom", "Mizuki", "Sami" })
            {
                string confirm = theme + "@Roguelike@NativeSettlementConfirm";
                string template = theme is "JieGarden" or "Sarkaz" ? theme + "@RoguelikeSettlementConfirm.png" : "RoguelikeSettlementConfirm.png";
                string afterFailed = theme + "@Roguelike@ClickToStartPointAfterFailed";
                tasks[confirm] = new JsonObject {
                    ["algorithm"] = "MatchTemplate",
                    ["template"] = template,
                    ["action"] = "ClickSelf",
                    ["roi"] = new JsonArray(500, 540, 280, 180),
                    ["postDelay"] = 300,
                    ["next"] = new JsonArray(afterFailed),
                };
                tasks[afterFailed] = new JsonObject {
                    ["baseTask"] = "Roguelike@ClickToStartPointAfterFailed",
                    ["next"] = new JsonArray(confirm, theme + "@Roguelike@StartExplore", theme + "@Roguelike@StartExploreCD", theme + "@Roguelike@StartUpThemes#next", afterFailed),
                };
            }

            const string candleSelect = "JieGarden@Roguelike@NativeCandleSelect";
            const string candleConfirm = "JieGarden@Roguelike@NativeCandleConfirm";

            // This event uses the owned-operator list, not the recruitment screen.
            // The confirmation label gates the fixed first-card selection.
            tasks[candleSelect] = new JsonObject {
                ["algorithm"] = "OcrDetect",
                ["text"] = new JsonArray("确认秉烛"),
                ["roi"] = new JsonArray(1030, 620, 250, 100),
                ["action"] = "ClickRect",
                ["specificRect"] = new JsonArray(320, 115, 80, 50),
                ["screenAnchor"] = "center",
                ["postDelay"] = 300,
                ["next"] = new JsonArray(candleConfirm),
            };
            tasks[candleConfirm] = new JsonObject {
                ["algorithm"] = "OcrDetect",
                ["text"] = new JsonArray("确认秉烛"),
                ["roi"] = new JsonArray(1030, 620, 250, 100),
                ["action"] = "ClickSelf",
                ["postDelay"] = 500,
                ["next"] = new JsonArray(candleSelect, "JieGarden@Roguelike@ClickToDrops"),
            };
            foreach (string entry in new[] { "Roguelike@Begin", "Roguelike@ClickToDrops" })
            {
                var candidates = tasks[entry]!["next"]!.AsArray();
                if (!candidates.Any(candidate => candidate?.GetValue<string>() == candleSelect))
                {
                    candidates.Insert(0, JsonValue.Create(candleSelect));
                }
            }

            string rogueTemporary = roguePath + ".native.tmp";
            File.WriteAllText(rogueTemporary, tasks.ToJsonString());
            File.Move(rogueTemporary, roguePath, true);
        }

        string gardenPath = Path.Combine(resourceDirectory, "tasks", "Roguelike", "JieGarden.json");
        if (File.Exists(gardenPath))
        {
            var garden = JsonNode.Parse(File.ReadAllText(gardenPath))!.AsObject();
            const string trader = "JieGarden@Roguelike@StageTrader";
            const string recovery = "JieGarden@Roguelike@NativeTraderMapRecovery";
            garden[trader]!["postDelay"] = 800;
            garden[recovery] = new JsonObject {
                ["algorithm"] = "OcrDetect",
                ["text"] = new JsonArray("诡意行商"),
                ["roi"] = new JsonArray(0, 80, 1000, 520),
                ["maxTimes"] = 2,
                ["next"] = new JsonArray(trader),
            };
            var enterNext = garden["JieGarden@Roguelike@StageTraderEnter"]!["next"]!.AsArray();
            if (!enterNext.Any(item => item?.GetValue<string>() == recovery))
            {
                enterNext.Add(recovery);
            }
            string gardenTemporary = gardenPath + ".native.tmp";
            File.WriteAllText(gardenTemporary, garden.ToJsonString());
            File.Move(gardenTemporary, gardenPath, true);
        }
    }

    internal static async Task<bool> EnsureStartedAsync(string adb, string serial)
    {
        if (string.IsNullOrWhiteSpace(serial) || !File.Exists(adb))
        {
            return false;
        }

        await _gate.WaitAsync(_lifetime.Token).ConfigureAwait(false);
        try
        {
            if (_adb == adb && _serial == serial && _server is { HasExited: false } && _ready)
            {
                return true;
            }

            await StopServerAsync().ConfigureAwait(false);
            _adb = adb;
            _serial = serial;
            await StartServerAsync().ConfigureAwait(false);
            _monitor ??= Task.Run(MonitorAsync);
            return true;
        }
        catch (Exception ex)
        {
            _ready = false;
            await StopServerAsync().ConfigureAwait(false);
            _logger.Warning(ex, "Native capture unavailable; standard ADB capture remains enabled");
            return false;
        }
        finally
        {
            _gate.Release();
        }
    }

    private static async Task<string> AdbAsync(params string[] arguments)
    {
        var info = new ProcessStartInfo(_adb) {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (string argument in arguments)
        {
            info.ArgumentList.Add(argument);
        }

        using var process = Process.Start(info)!;
        var output = process.StandardOutput.ReadToEndAsync();
        var errors = process.StandardError.ReadToEndAsync();
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        try
        {
            await process.WaitForExitAsync(deadline.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            process.Kill();
            throw;
        }

        if (process.ExitCode != 0)
        {
            throw new IOException(await errors.ConfigureAwait(false));
        }

        return await output.ConfigureAwait(false);
    }

    private static async Task<bool> RequestAsync(byte request, CancellationToken token)
    {
        try
        {
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
            deadline.CancelAfter(TimeSpan.FromMilliseconds(1500));
            using var client = new TcpClient { NoDelay = true };
            await client.ConnectAsync(IPAddress.Loopback, Port, deadline.Token).ConfigureAwait(false);
            await using var stream = client.GetStream();
            await stream.WriteAsync(new byte[] { request }, deadline.Token).ConfigureAwait(false);
            var acknowledgement = new byte[1];
            await stream.ReadExactlyAsync(acknowledgement, deadline.Token).ConfigureAwait(false);
            return acknowledgement[0] == (byte)'K';
        }
        catch (Exception ex) when (ex is IOException or SocketException or OperationCanceledException)
        {
            return false;
        }
    }

    private static async Task StartServerAsync()
    {
        if (_serial.Contains(':'))
        {
            await AdbAsync("connect", _serial).ConfigureAwait(false);
        }
        if ((await AdbAsync("-s", _serial, "get-state").ConfigureAwait(false)).Trim() != "device")
        {
            throw new IOException("ADB device is offline or unauthorized");
        }

        string expected = $"{_serial} tcp:{Port} localabstract:maa-native-cap";
        string mappings = await AdbAsync("forward", "--list").ConfigureAwait(false);
        if (mappings.Split('\n').Select(line => line.Trim()).Any(line => line.Contains($" tcp:{Port} ", StringComparison.Ordinal) && line != expected))
        {
            throw new IOException("Native capture port is owned by another forwarding entry");
        }

        await AdbAsync("-s", _serial, "forward", $"tcp:{Port}", "localabstract:maa-native-cap").ConfigureAwait(false);
        _ownsForward = true;
        await RequestAsync((byte)'Q', CancellationToken.None).ConfigureAwait(false);
        await Task.Delay(200, _lifetime.Token).ConfigureAwait(false);
        string directory = Path.Combine(PathsHelper.BaseDir, "cache", "native-capture");
        Directory.CreateDirectory(directory);
        string jarPath = Path.Combine(directory, "maa-native-cap.jar");
        await using (var embedded = Assembly.GetExecutingAssembly().GetManifestResourceStream("NativeCapture.MaaNativeCap.jar")!)
        await using (var file = File.Create(jarPath))
        {
            await embedded.CopyToAsync(file, _lifetime.Token).ConfigureAwait(false);
        }

        await AdbAsync("-s", _serial, "push", jarPath, "/data/local/tmp/maa-native-cap.jar").ConfigureAwait(false);
        var info = new ProcessStartInfo(_adb) {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (string argument in new[] { "-s", _serial, "shell", "CLASSPATH=/data/local/tmp/maa-native-cap.jar app_process /system/bin MaaNativeCap --serve" })
        {
            info.ArgumentList.Add(argument);
        }

        _server = Process.Start(info)!;
        _server.OutputDataReceived += (_, e) => {
            if (e.Data is not null)
            {
                _logger.Debug("Native capture: {Output}", e.Data);
            }
        };
        _server.ErrorDataReceived += (_, e) => {
            if (e.Data is not null)
            {
                if (e.Data.StartsWith("frame ", StringComparison.Ordinal))
                {
                    _logger.Debug("Native capture: {Output}", e.Data);
                }
                else
                {
                    _logger.Warning("Native capture: {Output}", e.Data);
                }
            }
        };
        _server.BeginOutputReadLine();
        _server.BeginErrorReadLine();
        for (int attempt = 0; attempt < 8; ++attempt)
        {
            await Task.Delay(200, _lifetime.Token).ConfigureAwait(false);
            if (await RequestAsync((byte)'P', _lifetime.Token).ConfigureAwait(false))
            {
                _ready = true;
                _logger.Information("Integrated native capture ready for {Serial}", _serial);
                return;
            }
        }

        throw new IOException("Native capture service did not become ready");
    }

    private static async Task MonitorAsync()
    {
        int failures = 0;
        while (!_lifetime.IsCancellationRequested)
        {
            try
            {
                bool healthy = await RequestAsync((byte)'P', _lifetime.Token).ConfigureAwait(false);
                failures = healthy ? 0 : failures + 1;
                if (failures >= 3 || _server is { HasExited: true })
                {
                    await _gate.WaitAsync(_lifetime.Token).ConfigureAwait(false);
                    try
                    {
                        await StopServerAsync().ConfigureAwait(false);
                        await StartServerAsync().ConfigureAwait(false);
                        failures = 0;
                    }
                    finally
                    {
                        _gate.Release();
                    }
                }

                await Task.Delay(150, _lifetime.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.Warning(ex, "Integrated native capture recovery failed");
                try
                {
                    await Task.Delay(3000, _lifetime.Token).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    break;
                }
            }
        }
    }

    private static async Task StopServerAsync()
    {
        _ready = false;
        if (_ownsForward)
        {
            await RequestAsync((byte)'Q', CancellationToken.None).ConfigureAwait(false);
            try
            {
                await AdbAsync("-s", _serial, "forward", "--remove", $"tcp:{Port}").ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                _logger.Warning(ex, "Could not remove native capture forwarding entry");
            }

            _ownsForward = false;
        }

        if (_server is not null)
        {
            if (!_server.HasExited)
            {
                using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(2));
                try
                {
                    await _server.WaitForExitAsync(deadline.Token).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    _server.Kill();
                }
            }

            _server.Dispose();
            _server = null;
        }
    }

    internal static async Task StopAsync()
    {
        await _lifetime.CancelAsync().ConfigureAwait(false);
        if (_monitor is not null)
        {
            await _monitor.ConfigureAwait(false);
        }

        await _gate.WaitAsync().ConfigureAwait(false);
        try
        {
            await StopServerAsync().ConfigureAwait(false);
        }
        finally
        {
            _gate.Release();
        }
    }
}
