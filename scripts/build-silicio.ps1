param(
 [Parameter(Mandatory)][string]$SourceDir,
 [Parameter(Mandatory)][string]$ControlDir,
 [Parameter(Mandatory)][string]$OutputDir
)
$ErrorActionPreference='Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or !$IsWindows) { throw 'Somente runner Windows; nao executar build local.' }
$SourceDir=(Resolve-Path -LiteralPath $SourceDir).Path
$ControlDir=(Resolve-Path -LiteralPath $ControlDir).Path
$Workspace=(Resolve-Path -LiteralPath $env:GITHUB_WORKSPACE).Path
$OutputDir=[IO.Path]::GetFullPath($OutputDir)
foreach ($TargetPath in @($SourceDir,$ControlDir,$OutputDir)) {
 if (!$TargetPath.StartsWith($Workspace+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Fora do workspace remoto' }
}
if (Test-Path -LiteralPath $OutputDir) { throw 'Saida deve ser nova' }
$BaseCommit='e968eae18407ea557064c32f4fdcea96464f5372'
$Actual=(& git -C $SourceDir rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $Actual -ne $BaseCommit) { throw 'Revisao incorreta' }
$Dirty=& git -C $SourceDir status --porcelain
if ($LASTEXITCODE -ne 0 -or $Dirty) { throw 'Fonte inicial deve estar limpo' }
foreach ($Part in @('bin','source','evidence','recipe')) { New-Item -ItemType Directory -Path (Join-Path $OutputDir $Part) -Force | Out-Null }
function Invoke-Checked {
 param([string]$Program,[string[]]$Arguments,[string]$Log)
 if ($Log) { & $Program @Arguments 2>&1 | Tee-Object -FilePath $Log }
 else { & $Program @Arguments }
 if ($LASTEXITCODE -ne 0) { throw "$Program falhou: $LASTEXITCODE" }
}
$Evidence=Join-Path $OutputDir 'evidence'
$BuildDir=Join-Path $Workspace 'build-4449'
$BuildDrive=[IO.Path]::GetPathRoot($Workspace).TrimEnd([IO.Path]::DirectorySeparatorChar).TrimEnd(':')
$Disk=Get-PSDrive -Name $BuildDrive
if ($Disk.Free -lt 8GB) { throw 'Menos de 8 GiB livres; abortar antes de compilar' }
if (Test-Path -LiteralPath $BuildDir) { throw 'Build deve ser novo' }
$VsWhere=Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Microsoft Visual Studio\Installer\vswhere.exe'
$VsJson=& $VsWhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -format json
if ($LASTEXITCODE -ne 0) { throw 'vswhere falhou' }
$Vs=@($VsJson | ConvertFrom-Json)
if ($Vs.Count -ne 1 -or $Vs[0].installationVersion -notmatch '^17\.') { throw 'VS 2022 C++ ausente' }
$CmakeVersion=(& cmake --version | Select-Object -First 1)
if ($LASTEXITCODE -ne 0 -or $CmakeVersion -notmatch '^cmake version 3\.') { throw 'Revisar CMake; esperado 3.x' }
$PublicArchive=Join-Path $OutputDir 'source\upstream-source.zip'
Invoke-Checked -Program git -Arguments @('-C',$SourceDir,'archive','--format=zip',"--output=$PublicArchive",'HEAD')
Copy-Item -LiteralPath (Join-Path $SourceDir 'LICENSE') -Destination (Join-Path $OutputDir 'LICENSE')
# Patch de recursos somente na arvore efemera.
$Settings=Join-Path $SourceDir 'cmake\compiler\msvc\settings.cmake'
$SettingsText=Get-Content -Raw -LiteralPath $Settings
$Expected='set(MSVC_ADDITIONAL_FLAGS "${MSVC_ADDITIONAL_FLAGS} /MP")'
$Replacement='set(MSVC_ADDITIONAL_FLAGS "${MSVC_ADDITIONAL_FLAGS} /MP2")'
if (($SettingsText.Split([string[]]@($Expected),[StringSplitOptions]::None).Length-1) -ne 1) { throw 'Regra /MP divergente' }
[IO.File]::WriteAllText($Settings,$SettingsText.Replace($Expected,$Replacement),[Text.UTF8Encoding]::new($false))
$ResourcePatch=& git -C $SourceDir diff --binary -- cmake/compiler/msvc/settings.cmake
if ($LASTEXITCODE -ne 0) { throw 'Falha ao registrar diff' }
$ResourcePatch | Set-Content -LiteralPath (Join-Path $OutputDir 'source\resource.patch') -Encoding utf8
$PatchHash=$null
$Variant='silicio'
Invoke-Checked -Program python -Arguments @((Join-Path $ControlDir 'scripts\apply-silicio.py'),$SourceDir)
Invoke-Checked -Program git -Arguments @('-C',$SourceDir,'add','-N','src/game/PlayerBots/SilicioAI.inc')
$SilicioDiff=& git -C $SourceDir diff --binary -- src/game/PlayerBots/PlayerBotAI.cpp src/game/PlayerBots/SilicioAI.inc
if ($LASTEXITCODE -ne 0) { throw 'Cannot record Silicio patch' }
$SilicioDiff | Set-Content -LiteralPath (Join-Path $OutputDir 'source\silicio.patch') -Encoding utf8
$PatchHash=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $OutputDir 'source\silicio.patch')).Hash.ToLowerInvariant()

$CMakeArgs=@(
 '-S',$SourceDir,'-B',$BuildDir,'-G','Visual Studio 17 2022','-A','x64',
 '-DSUPPORTED_CLIENT_BUILD=4449','-DBUILD_FOR_HOST_CPU=OFF',
 '-DBUILD_EXTRACTORS=OFF','-DBUILD_REALMMERGE=OFF',
 '-DENABLE_MAILSENDER=OFF','-DENABLE_CPPTRACE=OFF','-DUSE_SCRIPTS=ON',
 '-DUSE_PCH=ON','-DUSE_PCH_OLD=OFF','-DBUILD_WARNINGS_AS_ERROR=OFF'
)
Invoke-Checked -Program cmake -Arguments $CMakeArgs -Log (Join-Path $Evidence 'configure.log')
$Progression=Get-Content -Raw -LiteralPath (Join-Path $SourceDir 'src\shared\Progression.h')
if ($Progression -notmatch '(?m)^#define SUPPORTED_CLIENT_BUILD 4449\s*$') { throw 'Header incorreto' }
$Cache=Get-Content -Raw -LiteralPath (Join-Path $BuildDir 'CMakeCache.txt')
if ($Cache -notmatch '(?m)^SUPPORTED_CLIENT_BUILD:STRING=4449\s*$') { throw 'Cache incorreto' }
Copy-Item -LiteralPath (Join-Path $SourceDir 'src\shared\Progression.h') -Destination (Join-Path $Evidence 'Progression.h')
$Watch=[Diagnostics.Stopwatch]::StartNew()
Invoke-Checked -Program cmake -Arguments @('--build',$BuildDir,'--config','Release','--target','mangosd','realmd','--parallel','1','--','/m:1') -Log (Join-Path $Evidence 'build.log')
$Watch.Stop()
foreach ($Exe in @('mangosd.exe','realmd.exe')) { Copy-Item -LiteralPath (Join-Path $SourceDir "bin\Release\$Exe") -Destination (Join-Path $OutputDir "bin\$Exe") }
foreach ($Dll in @('libmySQL.dll','libeay32.dll')) { Copy-Item -LiteralPath (Join-Path $SourceDir "dep\windows\lib\x64_release\$Dll") -Destination (Join-Path $OutputDir "bin\$Dll") }
foreach ($ScriptName in @('build-silicio.ps1','verify_artifact.py')) { Copy-Item -LiteralPath (Join-Path $ControlDir "scripts\$ScriptName") -Destination (Join-Path $OutputDir ("recipe\" + $ScriptName.Replace("build-silicio.ps1","build.ps1"))) }
Copy-Item -LiteralPath (Join-Path $ControlDir '.github\workflows\silicio-ai.yml') -Destination (Join-Path $OutputDir 'recipe\silicio-4449.yml')
$FileManifest=@()
foreach ($File in (Get-ChildItem -LiteralPath $OutputDir -Recurse -File | Sort-Object FullName)) {
 $Relative=[IO.Path]::GetRelativePath($OutputDir,$File.FullName).Replace('\','/')
 $FileManifest+=@{path=$Relative;size=$File.Length;sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $File.FullName).Hash.ToLowerInvariant()}
}
$Manifest=@{
 schema=1;upstream_repository='vmangos/core';upstream_commit=$BaseCommit;
 client_build=4449;configuration='Release';architecture='x64';variant=$Variant;
 silicio_patch_sha256=$PatchHash;build_seconds=[Math]::Round($Watch.Elapsed.TotalSeconds,2);
 control_repository=$env:GITHUB_REPOSITORY;control_commit=$env:GITHUB_SHA;
 run_id=$env:GITHUB_RUN_ID;run_attempt=$env:GITHUB_RUN_ATTEMPT;
 image_os=$env:ImageOS;image_version=$env:ImageVersion;
 visual_studio=$Vs[0].installationVersion;cmake=$CmakeVersion;
 cmake_arguments=$CMakeArgs;compiler_parallelism=2;msbuild_parallelism=1;
 notes='Compilation only. No server run, maps, live configuration or database.';
 files=$FileManifest
}
$PayloadBytes=(Get-ChildItem -LiteralPath $OutputDir -Recurse -File | Measure-Object -Property Length -Sum).Sum
if ($PayloadBytes -gt 200MB) { throw 'Pacote excede limite planejado de 200 MiB; nao fazer upload' }
$Manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDir 'manifest.json') -Encoding utf8
