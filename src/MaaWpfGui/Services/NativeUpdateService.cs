// <copyright file="NativeUpdateService.cs" company="MaaAssistantArknights">
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
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using MaaWpfGui.Helper;
using MaaWpfGui.ViewModels.UI;
using MaaWpfGui.ViewModels.UserControl.Settings;
using Newtonsoft.Json.Linq;
using Semver;
using Serilog;
using static MaaWpfGui.ViewModels.Dialogs.VersionUpdateDialogViewModel;

namespace MaaWpfGui.Services;

internal static class NativeUpdateService
{
    internal const string Repository = "kevin07429/MAA-Native";
    private static readonly ILogger _logger = Log.ForContext(typeof(NativeUpdateService));

    internal static string GetCompatibilityVersion(string version)
    {
        var match = Regex.Match(version, @"^v?(\d+\.\d+\.\d+)-native\.\d+(?:\+[0-9A-Za-z.-]+)?$");
        return match.Success ? "v" + match.Groups[1].Value : version;
    }

    internal static string? GetProgramAssetName(JObject release, string currentVersion, bool allowSameVersion = false)
    {
        string tag = release["tag_name"]?.Value<string>() ?? string.Empty;
        if (release["draft"]?.Value<bool>() == true || release["prerelease"]?.Value<bool>() == true ||
            !Regex.IsMatch(tag, @"^v\d+\.\d+\.\d+-native\.\d+$") ||
            !SemVersion.TryParse(tag, SemVersionStyles.AllowLowerV, out var target) ||
            !SemVersion.TryParse(currentVersion, SemVersionStyles.AllowLowerV, out var current) ||
            (target.CompareSortOrderTo(current) < 0 || (!allowSameVersion && target.CompareSortOrderTo(current) == 0)))
        {
            return null;
        }

        string name = $"MAA-Native-{tag}-program-win-x64.zip";
        return release["assets"]?.Any(asset => asset["name"]?.Value<string>() == name) == true ? name : null;
    }

    internal static bool ValidateProgramArchive(string path)
    {
        using var archive = ZipFile.OpenRead(path);
        bool hasCore = false, hasUi = false;
        foreach (var entry in archive.Entries)
        {
            string name = entry.FullName.Replace('\\', '/');
            string[] parts = name.Split('/');
            if (name.StartsWith('/') || name.Contains(':') || parts.Any(part => part is ".." or ".") ||
                new[] { "config", "cache", "data", "debug", "resource", "optimization" }.Contains(parts[0], StringComparer.OrdinalIgnoreCase))
            {
                return false;
            }
            hasCore |= name.Equals("MaaCore.dll", StringComparison.OrdinalIgnoreCase);
            hasUi |= name.Equals("MAA.dll", StringComparison.OrdinalIgnoreCase);
            if (name.Equals("removelist.txt", StringComparison.OrdinalIgnoreCase))
            {
                using var reader = new StreamReader(entry.Open());
                if (!string.IsNullOrWhiteSpace(reader.ReadToEnd()))
                {
                    return false;
                }
            }
            if (name.Equals("changes.json", StringComparison.OrdinalIgnoreCase))
            {
                using var reader = new StreamReader(entry.Open());
                var changes = JObject.Parse(reader.ReadToEnd());
                if (changes["deleted"] is JArray deleted && deleted.Count != 0)
                {
                    return false;
                }
            }
        }
        return hasCore && hasUi && archive.GetEntry("changes.json") is not null;
    }

    private static Uri GetAssetUri(JToken asset)
    {
        var uri = new Uri(asset["browser_download_url"]!.Value<string>()!);
        if (uri.Scheme != "https" || uri.Host != "github.com" ||
            !uri.AbsolutePath.StartsWith($"/{Repository}/releases/download/", StringComparison.Ordinal))
        {
            throw new InvalidDataException("Unexpected native update asset URL");
        }
        return uri;
    }

    internal static Uri[] GetMirrorAssetUris(Uri uri)
    {
        if (uri.Scheme != Uri.UriSchemeHttps || uri.Host != "github.com" ||
            !uri.AbsolutePath.StartsWith($"/{Repository}/releases/download/", StringComparison.Ordinal))
        {
            throw new InvalidDataException("Unexpected native update asset URL");
        }

        return [
            new Uri("https://gh-proxy.com/" + uri.AbsoluteUri),
            new Uri("https://ghfast.top/" + uri.AbsoluteUri),
        ];
    }

    internal static Uri[] GetAssetDownloadUris(Uri uri)
    {
        return [.. GetMirrorAssetUris(uri), uri];
    }

    private static async Task<string?> GetAssetTextAsync(Uri uri)
    {
        foreach (Uri candidate in GetAssetDownloadUris(uri))
        {
            string? result = await Instances.HttpService.GetStringAsync(candidate).ConfigureAwait(false);
            if (!string.IsNullOrWhiteSpace(result))
            {
                return result;
            }
        }

        return null;
    }

    private static async Task<bool> DownloadAssetAsync(Uri uri, string path)
    {
        foreach (Uri candidate in GetAssetDownloadUris(uri))
        {
            if (await Instances.HttpService.DownloadFileAsync(candidate, path).ConfigureAwait(false))
            {
                return true;
            }
        }

        return false;
    }

    private static async Task<HttpResponseMessage> GetLatestReleaseResponseAsync()
    {
        Uri uri = new($"https://api.github.com/repos/{Repository}/releases/latest");
        foreach (Uri candidate in GetReleaseLookupUris(uri))
        {
            try
            {
                var response = await Instances.HttpService.GetAsync(candidate).ConfigureAwait(false);
                if (response.IsSuccessStatusCode || response.StatusCode == System.Net.HttpStatusCode.NotFound)
                {
                    return response;
                }

                _logger.Warning(
                    "Native release lookup through {Host} returned {StatusCode}",
                    candidate.Host,
                    response.StatusCode);
                response.Dispose();
            }
            catch (Exception exception)
            {
                _logger.Warning(exception, "Native release lookup failed through {Host}", candidate.Host);
            }
        }

        throw new HttpRequestException("Native release information is unavailable from domestic mirrors and GitHub");
    }

    private static Uri[] GetMirrorApiUris(Uri uri)
    {
        if (uri.Scheme != Uri.UriSchemeHttps || uri.Host != "api.github.com" ||
            uri.AbsolutePath != $"/repos/{Repository}/releases/latest" ||
            !string.IsNullOrEmpty(uri.Query) || !string.IsNullOrEmpty(uri.Fragment))
        {
            throw new InvalidDataException("Unexpected native release API URL");
        }

        return [new Uri("https://gh-proxy.com/" + uri.AbsoluteUri)];
    }

    internal static Uri[] GetReleaseLookupUris(Uri uri)
    {
        return [.. GetMirrorApiUris(uri), uri];
    }

    internal static async Task<CheckUpdateRetT> CheckAndDownloadAsync(bool allowSameVersion = false)
    {
        var settings = SettingsViewModel.VersionUpdateSettings;
        if (settings.IsCheckingForUpdates)
        {
            return CheckUpdateRetT.NoNeedToUpdate;
        }
        settings.IsCheckingForUpdates = true;
        string? temporary = null;
        try
        {
            using var response = await GetLatestReleaseResponseAsync();
            if (response.StatusCode == System.Net.HttpStatusCode.NotFound)
            {
                return CheckUpdateRetT.AlreadyLatest;
            }
            response.EnsureSuccessStatusCode();
            var release = JObject.Parse(await response.Content.ReadAsStringAsync());
            string current = VersionUpdateSettingsUserControlModel.UiVersion;
            string? assetName = GetProgramAssetName(release, current, allowSameVersion);
            if (assetName is null)
            {
                settings.NewVersionFoundInfo = LocalizationHelper.GetString("Settings.Update.AlreadyLatest");
                return CheckUpdateRetT.AlreadyLatest;
            }
            string tag = release["tag_name"]!.Value<string>()!;
            settings.NewVersionFoundInfo = $"{LocalizationHelper.GetString("VersionUpdate.NewVersionFound.Title")}: {tag}";
            var assets = (JArray)release["assets"]!;
            var asset = assets.First(item => item["name"]!.Value<string>() == assetName);
            var checksum = assets.FirstOrDefault(item => item["name"]?.Value<string>() == assetName + ".sha256");
            if (checksum is null)
            {
                return CheckUpdateRetT.FailedToGetInfo;
            }
            string? checksumText = await GetAssetTextAsync(GetAssetUri(checksum));
            var match = Regex.Match(checksumText ?? string.Empty, @"\A([a-fA-F0-9]{64})(?:\s|$)");
            if (!match.Success)
            {
                return CheckUpdateRetT.FailedToGetInfo;
            }
            string folder = Path.Combine(PathsHelper.CacheDir, "native-update");
            Directory.CreateDirectory(folder);
            temporary = Path.Combine(folder, assetName + ".download");
            OutputDownloadProgress(LocalizationHelper.GetString("VersionUpdate.NewVersionDownloading.GlobalSource") + " " + tag, downloading: true);
            if (!await DownloadAssetAsync(GetAssetUri(asset), temporary))
            {
                return CheckUpdateRetT.UpdatePackageDownloadFailed;
            }
            await using (var stream = File.OpenRead(temporary))
            {
                string hash = Convert.ToHexString(await SHA256.HashDataAsync(stream));
                if (!hash.Equals(match.Groups[1].Value, StringComparison.OrdinalIgnoreCase))
                {
                    throw new InvalidDataException("Native update SHA256 mismatch");
                }
            }
            if (!ValidateProgramArchive(temporary))
            {
                throw new InvalidDataException("Native update package is not a program-only update");
            }
            string package = Path.Combine(folder, $"MAAComponent-OTA-{current}_{tag}-win-x64.zip");
            File.Move(temporary, package, true);
            temporary = null;
            if (allowSameVersion && tag == current)
            {
                Instances.VersionUpdateDialogViewModel.UpdatePackageName = package;
            }
            else
            {
                var imported = PendingUpdateApplier.TryRegisterLocalPackage(package, current, "x64", inspection: null);
                if (imported.Status != PendingUpdateApplier.LocalPackageImportStatus.OtaPackageRegistered)
                {
                    return CheckUpdateRetT.UpdatePackageDownloadFailed;
                }
            }
            Instances.VersionUpdateDialogViewModel.UpdateTag = tag;
            OutputDownloadProgress(LocalizationHelper.GetString("VersionUpdate.NewVersionDownloadCompleted.Title"), downloading: false);
            return CheckUpdateRetT.OK;
        }
        catch (Exception exception)
        {
            _logger.Error(exception, "Native GitHub update failed");
            OutputDownloadProgress(LocalizationHelper.GetString("VersionUpdate.NewVersionDetectFailed.Title"), downloading: false);
            return CheckUpdateRetT.NetworkError;
        }
        finally
        {
            if (temporary is not null && File.Exists(temporary))
            {
                try
                {
                    File.Delete(temporary);
                }
                catch (IOException exception)
                {
                    _logger.Warning(exception, "Could not remove incomplete native update");
                }
            }
            settings.IsCheckingForUpdates = false;
        }
    }
}
