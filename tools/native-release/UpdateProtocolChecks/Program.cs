// <copyright file="Program.cs" company="MaaAssistantArknights">
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

using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.Loader;
using Newtonsoft.Json.Linq;

string gui = Path.GetFullPath(args[0]);
AssemblyLoadContext.Default.Resolving += (_, name) => {
    string path = Path.Combine(gui, name.Name + ".dll");
    return File.Exists(path) ? AssemblyLoadContext.Default.LoadFromAssemblyPath(path) : null;
};
var assembly = Assembly.LoadFrom(Path.Combine(gui, "MAA.dll"));
if (args.Length > 1 && assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion.Split('+')[0] != args[1]) {
    throw new Exception("GUI release version mismatch");
}
if (args.Length > 2) {
    var prepare=assembly.GetType("MaaWpfGui.Services.NativeCaptureService",true)!.GetMethod("PrepareResources",BindingFlags.Static|BindingFlags.NonPublic)!;
    prepare.Invoke(null,[Path.GetFullPath(args[2])]);
    string resource = Path.GetFullPath(args[2]);
    var tasks = JObject.Parse(File.ReadAllText(Path.Combine(resource,"tasks","Roguelike","base.json")));
    var templates = tasks["Roguelike"]!["template"]!.Values<string>().ToHashSet();
    var files = Directory.EnumerateFiles(Path.Combine(resource,"template"),"*.png",SearchOption.AllDirectories)
        .Select(path => path.Replace('\\','/')).ToArray();
    if (templates.Count == 0 || templates.Any(name => !files.Any(path => path.EndsWith("/"+name,StringComparison.Ordinal))))
        throw new Exception("Prepared Roguelike task references missing templates");
    foreach(string terminal in Directory.EnumerateFiles(Path.Combine(resource,"template","UiTheme"),"Terminal*.png",SearchOption.AllDirectories))
        if(!templates.Contains(Path.GetRelativePath(Path.Combine(resource,"template","UiTheme"),terminal).Replace('\\','/')))
            throw new Exception("A current or legacy terminal variant was omitted");
    Console.WriteLine("PASS: generated Roguelike templates exist and include current/legacy terminal variants");
    string strategyPath = Path.Combine(resource,"roguelike","BlackFlow","strategy.json");
    string originalStrategy = File.ReadAllText(strategyPath);
    var legacyStrategy = JObject.Parse(originalStrategy);
    using var defaultStrategyStream = assembly.GetManifestResourceStream("NativeCapture.BlackFlowStrategy.json")!;
    using var defaultStrategyReader = new StreamReader(defaultStrategyStream);
    var expectedRewards = JObject.Parse(defaultStrategyReader.ReadToEnd())["last_reward_orders"]!.DeepClone();
    legacyStrategy.Remove("last_reward_orders");
    File.WriteAllText(strategyPath,legacyStrategy.ToString());
    prepare.Invoke(null,[resource]);
    var migrated = JObject.Parse(File.ReadAllText(strategyPath));
    if(!JToken.DeepEquals(migrated["last_reward_orders"],expectedRewards) || legacyStrategy.Properties().Any(p => !JToken.DeepEquals(p.Value,migrated[p.Name])))
        throw new Exception("Legacy resource migration lost settings or required reward defaults");
    File.WriteAllText(strategyPath,originalStrategy);
    Console.WriteLine("PASS: legacy BlackFlow resource defaults restored without overwriting existing settings");
}
var service = assembly.GetType("MaaWpfGui.Services.NativeUpdateService", true)!;
var compatibility = service.GetMethod("GetCompatibilityVersion", BindingFlags.Static | BindingFlags.NonPublic)!;
foreach (var (input, expected) in new[] { ("v6.21.1-native.6", "v6.21.1"), ("v6.21.0-native.5", "v6.21.0"), ("v6.21.1-beta.1", "v6.21.1-beta.1"), ("v6.21.1", "v6.21.1"), ("v6.21.1-native.7+abcdef", "v6.21.1") })
    Check((string)compatibility.Invoke(null,[input])! == expected,"feature compatibility uses upstream base: " + input);
var resolve = service.GetMethod("GetProgramAssetName", BindingFlags.Static | BindingFlags.NonPublic)!;
var mirrorUris = service.GetMethod("GetMirrorAssetUris", BindingFlags.Static | BindingFlags.NonPublic)!;
var apiMirrorUris = service.GetMethod("GetMirrorApiUris", BindingFlags.Static | BindingFlags.NonPublic)!;
var assetUris = service.GetMethod("GetAssetDownloadUris", BindingFlags.Static | BindingFlags.NonPublic)!;
var releaseUris = service.GetMethod("GetReleaseLookupUris", BindingFlags.Static | BindingFlags.NonPublic)!;
var validate = service.GetMethod("ValidateProgramArchive", BindingFlags.Static | BindingFlags.NonPublic)!;
var inspect = assembly.GetType("MaaWpfGui.Services.PendingUpdateApplier", true)!.GetMethod("InspectLocalUpdatePackage")!;
const string asset = "MAA-Native-v6.20.1-native.3-program-win-x64.zip";
JObject Release(string version = "v6.20.1-native.3") => new() {
    ["tag_name"] = version, ["draft"] = false, ["prerelease"] = false,
    ["assets"] = new JArray(new JObject { ["name"] = asset }),
};
string? Resolve(JObject release, string current = "v6.20.1-native.2", bool repair = false) =>
    (string?)resolve.Invoke(null, [release, current, repair]);
void Check(bool condition, string description) {
    if (!condition) throw new Exception(description);
    Console.WriteLine("PASS: " + description);
}
Check(Resolve(Release()) == asset, "native upgrade selects only its x64 program asset");
var mirrors = (Uri[])mirrorUris.Invoke(null, [new Uri("https://github.com/kevin07429/MAA-Native/releases/download/v6.20.1-native.3/" + asset)])!;
Check(mirrors.Length == 2 && mirrors[0].Host == "gh-proxy.com" && mirrors[1].Host == "ghfast.top", "native update has two domestic asset mirrors");
var apiMirrors = (Uri[])apiMirrorUris.Invoke(null, [new Uri("https://api.github.com/repos/kevin07429/MAA-Native/releases/latest")])!;
Check(apiMirrors.Length == 1 && apiMirrors[0].Host == "gh-proxy.com", "native update has a domestic release lookup mirror");
var orderedAssets = (Uri[])assetUris.Invoke(null, [new Uri("https://github.com/kevin07429/MAA-Native/releases/download/v6.20.1-native.3/" + asset)])!;
Check(orderedAssets.Length == 3 && orderedAssets[0].Host == "gh-proxy.com" && orderedAssets[1].Host == "ghfast.top" && orderedAssets[2].Host == "github.com", "native assets use domestic mirrors before GitHub");
var orderedReleases = (Uri[])releaseUris.Invoke(null, [new Uri("https://api.github.com/repos/kevin07429/MAA-Native/releases/latest")])!;
Check(orderedReleases.Length == 2 && orderedReleases[0].Host == "gh-proxy.com" && orderedReleases[1].Host == "api.github.com", "native release lookup uses a domestic mirror before GitHub");
try {
    mirrorUris.Invoke(null, [new Uri("https://example.com/file.zip")]);
    throw new Exception("An unrelated URL was accepted as a mirror source");
} catch (TargetInvocationException exception) when (exception.InnerException is InvalidDataException) {
    Check(true, "untrusted asset URLs are rejected by mirror resolution");
}
Check(Resolve(Release(), "v6.20.1-native.3") is null, "equal version is not reinstalled automatically");
Check(Resolve(Release(), "v6.20.1-native.4") is null, "downgrade rejected");
Check(Resolve(Release(), "v6.20.1-native.3", true) == asset, "explicit repair permits the same version");
Check(Resolve(Release("v6.20.2")) is null, "upstream app release is rejected");
var draft = Release(); draft["draft"] = true;
Check(Resolve(draft) is null, "draft is not an update");
var prerelease = Release(); prerelease["prerelease"] = true;
Check(Resolve(prerelease) is null, "prerelease is not a stable update");
var arm = Release(); arm["assets"]![0]!["name"] = asset.Replace("x64", "arm64");
Check(Resolve(arm) is null, "wrong architecture rejected");
string fixture = Path.Combine(Path.GetTempPath(), "MAA-Native-UpdateChecks-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(fixture);
int index = 0;
string Zip(params (string Name, string Content)[] extras) {
    string path = Path.Combine(fixture, ++index + ".zip");
    using var archive = ZipFile.Open(path, ZipArchiveMode.Create);
    foreach (var item in new[] { ("MAA.dll", "ui"), ("MaaCore.dll", "core"), ("changes.json", "{\"deleted\":[]}") }.Concat(extras)) {
        using var writer = new StreamWriter(archive.CreateEntry(item.Item1).Open());
        writer.Write(item.Item2);
    }
    return path;
}
bool Valid(string path) => (bool)validate.Invoke(null, [path])!;
Check(Valid(Zip()), "program-only update accepted");
var declared=assembly.GetType("MaaWpfGui.Main.Bootstrapper",true)!.GetMethod("GetDeclaredRuntimeDlls",BindingFlags.Static|BindingFlags.NonPublic)!;
var dependencies=(HashSet<string>)declared.Invoke(null,[Path.Combine(gui,"MAA.deps.json")])!;
Check(dependencies.Contains("System.Private.CoreLib.dll") && dependencies.Contains("Newtonsoft.Json.dll"),"self-contained runtime dependencies are recognized at startup");
Check(!dependencies.Contains("UnknownInjected.dll"),"unlisted foreign DLLs remain unknown");
var boot = assembly.GetType("MaaWpfGui.Main.Bootstrapper", true)!;
var archiveObsolete = boot.GetMethod("ArchiveObsoleteRuntimeDlls", BindingFlags.Static | BindingFlags.NonPublic)!;
string runtimeFixture = Path.Combine(fixture, "runtime-upgrade");
Directory.CreateDirectory(Path.Combine(runtimeFixture, ".old"));
const string legacyDac = "mscordaccore_amd64_amd64_10.0.1226.42308.dll";
const string currentDac = "mscordaccore_amd64_amd64_10.0.1426.52326.dll";
void Deps(string path, params string[] names) {
    var native = new JObject();
    foreach (string name in names) native["runtimes/win-x64/native/" + name] = new JObject();
    File.WriteAllText(path, new JObject { ["targets"] = new JObject { ["net10.0/win-x64"] = new JObject { ["runtime/10"] = new JObject { ["native"] = native } } } }.ToString());
}
Deps(Path.Combine(runtimeFixture,".old","MAA.deps.json"),legacyDac,"coreclr.dll");
Deps(Path.Combine(runtimeFixture,"MAA.deps.json"),currentDac,"coreclr.dll");
foreach (string name in new[] { legacyDac, currentDac, "coreclr.dll", "UnknownInjected.dll" }) File.WriteAllText(Path.Combine(runtimeFixture,name),name);
archiveObsolete.Invoke(null,[runtimeFixture]);
Check(!File.Exists(Path.Combine(runtimeFixture,legacyDac)) && Directory.GetFiles(Path.Combine(runtimeFixture,".old"),legacyDac,SearchOption.AllDirectories).Length == 1,"old runtime DLL archived before startup check");
Check(new[] {currentDac,"coreclr.dll","UnknownInjected.dll"}.All(name=>File.Exists(Path.Combine(runtimeFixture,name))),"current and unrelated DLLs are not removed or whitelisted");
archiveObsolete.Invoke(null,[runtimeFixture]);
Check(Directory.GetFiles(Path.Combine(runtimeFixture,".old"),legacyDac,SearchOption.AllDirectories).Length == 1,"runtime cleanup is repeatable without losing backups");
File.Delete(Path.Combine(runtimeFixture,".old","MAA.deps.json"));
File.WriteAllText(Path.Combine(runtimeFixture,legacyDac),legacyDac);
archiveObsolete.Invoke(null,[runtimeFixture]);
Check(File.Exists(Path.Combine(runtimeFixture,legacyDac)),"missing previous manifest never authorizes removal");
foreach (string bad in new[] { "config/gui.new.json", "data/private.json", "resource/tasks/tasks.json", "cache/debug-control.json", "../escape.txt", "..\\escape.txt", "C:/escape.txt" }) {
    Check(!Valid(Zip((bad, "overwrite"))), "protected or escaping path rejected: " + bad);
}
Check(!Valid(Zip(("removelist.txt", "config/gui.new.json"))), "deletion list rejected");
string ota = Path.Combine(fixture, "MAAComponent-OTA-v6.20.1-native.2_v6.20.1-native.3-win-x64.zip");
File.Copy(Zip(), ota);
string Status(string current) {
    var result = inspect.Invoke(null, [ota, current, "x64", false])!;
    return result.GetType().GetProperty("Status")!.GetValue(result)!.ToString()!;
}
Check(Status("v6.20.1-native.2") == "OtaSupported", "existing pending-update importer accepts native OTA naming");
Check(Status("v6.20.1-native.1") == "OtaRejected", "OTA source version must match");
Console.WriteLine("All native update protocol checks passed. Fixtures: " + fixture);
