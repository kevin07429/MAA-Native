param([Parameter(Mandatory=$true)][string]$Version)
$ErrorActionPreference='Stop'
if($Version -notmatch '^v([0-9]+\.[0-9]+\.[0-9]+)-native\.([0-9]+)$'){throw 'Invalid native release version'}
$fileVersion=$Matches[1]+'.'+$Matches[2]
function Invoke-Checked([scriptblock]$Command){ & $Command; if($LASTEXITCODE -ne 0){throw ('Build command failed: '+$Command)} }
$captureHash=[BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes(([IO.File]::ReadAllText((Join-Path (Get-Location) 'tools/wireless-native/MaaNativeCap.java'))).Replace("`r`n","`n")))).Replace('-','').ToLowerInvariant()
if($captureHash -ne (Get-Content tools/wireless-native/capture-source.sha256 -Raw).Trim()){
 throw 'Capture source changed. Run .github/scripts/build-capture-jar.ps1 with an Android SDK and commit the rebuilt JAR and source checksum.'
}
Invoke-Checked { python tools/maadeps-download.py x64-windows }
Invoke-Checked { cmake -B build-native --preset windows-publish-x64 -DBUILD_DEBUG_DEMO=OFF -DBUILD_RESOURCE_UPDATER=OFF -DBUILD_NATIVE_ADAPTIVE_TESTS=ON "-DNATIVE_APP_VERSION=$Version" }
Invoke-Checked { cmake --build build-native --config Debug --target MaaCore native_adaptive_tests task_pause_tests --parallel 4 }
Invoke-Checked { & build-native/bin/Debug/native_adaptive_tests.exe }
Invoke-Checked { & build-native/bin/Debug/task_pause_tests.exe }
Invoke-Checked { cmake --build build-native --config Release --target MaaCore MAA.Updater --parallel 4 }
$buildRoot=(Resolve-Path build-native).Path
Invoke-Checked { dotnet publish src/MaaWpfGui/MaaWpfGui.csproj -c Release -r win-x64 --self-contained true -p:DisableBeauty=True -p:Platform=x64 "-p:InformationalVersion=$Version" "-p:Version=$($Version.TrimStart('v'))" "-p:FileVersion=$fileVersion" "-p:AssemblyVersion=$fileVersion" -p:PostBuildEvent= "-p:SolutionDir=$buildRoot/" "-p:OutputPath=$buildRoot/gui-bin/" -o build-native/gui-publish }
$headers=@{'User-Agent'='MAA-Native-release'}
$framework=Invoke-RestMethod -Uri 'https://api.github.com/repos/MaaXYZ/MaaFramework/releases/tags/v5.13.0' -Headers $headers
$unitAsset=$framework.assets | Where-Object { $_.name -like '*win-x86_64*.zip' } | Select-Object -First 1
if(-not $unitAsset){throw 'MAA control-unit runtime not found'}
Invoke-WebRequest -Uri $unitAsset.browser_download_url -OutFile build-native/control-units.zip
Expand-Archive -LiteralPath build-native/control-units.zip -DestinationPath build-native/control-units
$runtime=Join-Path (Get-Location) 'build-native/runtime'
New-Item -ItemType Directory -Path $runtime | Out-Null
foreach($pattern in @('*AdbControlUnit*.dll','*Win32ControlUnit*.dll')){
 Get-ChildItem build-native/control-units -Recurse -File -Filter $pattern | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $runtime }
}
Copy-Item build-native/bin/Release/MAA.Updater.exe $runtime
Invoke-WebRequest -Uri 'https://github.com/MaaAssistantArknights/MaaResource/archive/refs/heads/main.zip' -OutFile build-native/official-resource.zip
Expand-Archive -LiteralPath build-native/official-resource.zip -DestinationPath build-native/official-resource
Copy-Item -LiteralPath resource -Destination build-native/merged-resource -Recurse
Copy-Item -Path build-native/official-resource/MaaResource-main/resource/* -Destination build-native/merged-resource -Recurse -Force
Invoke-WebRequest -Uri 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip' -OutFile build-native/platform-tools.zip
Expand-Archive -LiteralPath build-native/platform-tools.zip -DestinationPath build-native/adb
Invoke-Checked { python tools/native-release/package_native.py --gui build-native/gui-publish --core build-native/bin/Release --runtime build-native/runtime --resources build-native/merged-resource --adb build-native/adb/platform-tools --output build-native/assets --version $Version }

$guiPath=Join-Path (Get-Location) 'build-native/gui-publish'
$resourcePath=Join-Path (Get-Location) "build-native/assets/portable-$Version/resource"
Invoke-Checked { dotnet run --project tools/native-release/UpdateProtocolChecks/UpdateProtocolChecks.csproj "-p:NativeGuiDir=$guiPath" -- $guiPath $Version $resourcePath }
# The preparation hook rewrites local resource rules. Regenerate the full package manifest before uploading.
Invoke-Checked { python tools/native-release/finalize_native_package.py --output build-native/assets --version $Version }
Invoke-Checked { python tools/native-release/verify_native_package.py --folder "build-native/assets/portable-$Version" --debug-dll build-native/bin/Debug --version $Version }
