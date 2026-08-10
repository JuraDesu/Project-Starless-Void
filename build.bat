@echo off
setlocal

set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=client"
if not defined ENGINE_DIST if exist "%~dp0engine\sdk\engine-content-config.cmake" set "ENGINE_DIST=%~dp0engine"
if not defined ENGINE_DIST set "ENGINE_DIST=%~dp0..\out\engine"
if not defined GAME_OUTPUT_DIR set "GAME_OUTPUT_DIR=%~dp0out"
if not defined TOOLROOT set "TOOLROOT=C:\dev\external"
if not defined EMSDK set "EMSDK=%TOOLROOT%\emsdk"
if not defined CMAKE set "CMAKE=%TOOLROOT%\cmake\bin\cmake.exe"
if not defined NINJA_PATH set "NINJA_PATH=%TOOLROOT%\msys64\mingw64\bin\ninja.exe"
rem Keep local convenience while leaving the project CMake file portable.  Users
rem can override either variable directly or point TOOLROOT at their tool tree.
if not defined ASEPRITE if exist "%TOOLROOT%\aseprite\build\bin\aseprite.exe" set "ASEPRITE=%TOOLROOT%\aseprite\build\bin\aseprite.exe"
if not defined MSDF_ATLAS_GEN if exist "%TOOLROOT%\msdf-atlas-gen\msdf-atlas-gen.exe" set "MSDF_ATLAS_GEN=%TOOLROOT%\msdf-atlas-gen\msdf-atlas-gen.exe"
if not defined BUILD_PROFILE set "BUILD_PROFILE=Release"

if defined GAME_BUILD_DIR (
    set "BUILD_DIR=%GAME_BUILD_DIR%"
) else (
    set "BUILD_DIR=%~dp0build\%BUILD_PROFILE%"
)
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"

set "NEEDS_CONFIGURE="
if not exist "%BUILD_DIR%\build.ninja" set "NEEDS_CONFIGURE=1"
if defined RECONFIGURE set "NEEDS_CONFIGURE=1"
if defined NEEDS_CONFIGURE (
    "%CMAKE%" -S "%~dp0." -B "%BUILD_DIR%" -G Ninja ^
        -DCMAKE_TOOLCHAIN_FILE="%EMSDK%\upstream\emscripten\cmake\Modules\Platform\Emscripten.cmake" ^
        -DCMAKE_BUILD_TYPE=%BUILD_PROFILE% ^
        -DCMAKE_MAKE_PROGRAM="%NINJA_PATH%" ^
        -DENGINE_DIST="%ENGINE_DIST%" ^
        -DGAME_OUTPUT_DIR="%GAME_OUTPUT_DIR%" ^
        -DASEPRITE="%ASEPRITE%" ^
        -DMSDF_ATLAS_GEN="%MSDF_ATLAS_GEN%"
    if errorlevel 1 exit /b 1
)

if /I "%TARGET%"=="client" (
    "%CMAKE%" --build "%BUILD_DIR%" --target game_client
) else if /I "%TARGET%"=="codegen" (
    "%CMAKE%" --build "%BUILD_DIR%" --target content_codegen_check
) else (
    echo Unknown game target: %TARGET%
    exit /b 1
)
exit /b %ERRORLEVEL%
