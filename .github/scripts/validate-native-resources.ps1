param([Parameter(Mandatory=$true)][string]$Version)
$ErrorActionPreference='Stop'
if($Version -notmatch '^v([0-9]+\.[0-9]+\.[0-9]+)-native\.([0-9]+)$'){throw 'Invalid native version'}
$fileVersion=$Matches[1]+'.'+$Matches[2]
function Invoke-Checked([scriptblock]$Command){ & $Command; if($LASTEXITCODE -ne 0){throw ('Validation failed: '+$Command)} }
Invoke-Checked { python tools/maadeps-download.py x64-windows }
Invoke-Checked { cmake -B build-native --preset windows-publish-x64 -DBUILD_DEBUG_DEMO=OFF -DBUILD_RESOURCE_UPDATER=OFF -DBUILD_NATIVE_ADAPTIVE_TESTS=ON "-DNATIVE_APP_VERSION=$Version" }
Invoke-Checked { cmake --build build-native --config Debug --target MaaCore native_adaptive_tests task_pause_tests --parallel 4 }
Invoke-Checked { & build-native/bin/Debug/native_adaptive_tests.exe }
Invoke-Checked { & build-native/bin/Debug/task_pause_tests.exe }
$buildRoot=(Resolve-Path build-native).Path
Invoke-Checked { dotnet publish src/MaaWpfGui/MaaWpfGui.csproj -c Release -r win-x64 --self-contained true -p:DisableBeauty=True -p:Platform=x64 "-p:InformationalVersion=$Version" "-p:Version=$($Version.TrimStart('v'))" "-p:FileVersion=$fileVersion" "-p:AssemblyVersion=$fileVersion" -p:PostBuildEvent= "-p:SolutionDir=$buildRoot/" "-p:OutputPath=$buildRoot/gui-bin/" -o build-native/gui-publish }
# Validate the exact proposed resources, without a potentially older mirror overlay.
New-Item -ItemType Directory build-native/resource-candidate | Out-Null
Copy-Item -LiteralPath resource -Destination build-native/resource-candidate/resource -Recurse
$gui=(Resolve-Path build-native/gui-publish).Path
$candidate=(Resolve-Path build-native/resource-candidate/resource).Path
Invoke-Checked { dotnet run --project tools/native-release/UpdateProtocolChecks/UpdateProtocolChecks.csproj "-p:NativeGuiDir=$gui" -- $gui $Version $candidate }
Invoke-Checked { python -c "import sys; sys.path.insert(0, 'tools'); from maa_core_eval import CoreEval; CoreEval(dll_dir='build-native/bin/Debug', resource='build-native/resource-candidate').close()" }
