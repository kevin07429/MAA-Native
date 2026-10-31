param([string]$SdkRoot=$env:ANDROID_HOME)
$ErrorActionPreference='Stop'
if(-not (Test-Path -LiteralPath $SdkRoot)){throw 'Set ANDROID_HOME or pass -SdkRoot to an Android SDK installation'}
$platform=Get-ChildItem (Join-Path $SdkRoot 'platforms') -Directory | Where-Object {$_.Name -match '^android-[0-9]+$'} | Sort-Object {[int]($_.Name -replace 'android-','')} -Descending | Select-Object -First 1
$buildTools=Get-ChildItem (Join-Path $SdkRoot 'build-tools') -Directory | Where-Object {$_.Name -match '^[0-9]+\.[0-9]+\.[0-9]+$'} | Sort-Object {[version]$_.Name} -Descending | Select-Object -First 1
if(-not $platform -or -not $buildTools){throw 'Android platform and build-tools are required'}
$out=Join-Path (Get-Location) ('build-native/capture-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $out 'classes'),(Join-Path $out 'dex') -Force | Out-Null
$androidJar=Join-Path $platform.FullName 'android.jar'
& javac --release 8 -cp $androidJar -d (Join-Path $out 'classes') tools/wireless-native/MaaNativeCap.java
if($LASTEXITCODE -ne 0){throw 'Capture Java compilation failed'}
$classes=Get-ChildItem (Join-Path $out 'classes') -File -Filter '*.class'
& (Join-Path $buildTools.FullName 'd8.bat') --lib $androidJar --min-api 26 --output (Join-Path $out 'dex') @($classes.FullName)
if($LASTEXITCODE -ne 0){throw 'Capture DEX compilation failed'}
& jar cf tools/wireless-native/maa-native-cap.jar -C (Join-Path $out 'dex') classes.dex
if($LASTEXITCODE -ne 0){throw 'Capture JAR creation failed'}
[BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes(([IO.File]::ReadAllText((Join-Path (Get-Location) 'tools/wireless-native/MaaNativeCap.java'))).Replace("`r`n","`n")))).Replace('-','').ToLowerInvariant() | Set-Content tools/wireless-native/capture-source.sha256 -Encoding ascii
