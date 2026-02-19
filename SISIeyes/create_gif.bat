@echo off
echo Creating GIF background video...
echo ================================

REM Create spiffs_data directory
if not exist spiffs_data mkdir spiffs_data

REM Convert video to LVGL-compatible GIF
echo Converting 111.mp4 to LVGL-compatible GIF...
ffmpeg -i "E:\liusisi\Sisi\esp32_liusisi\111.mp4" -vf "scale=172:320,fps=5" -t 5 -loop 0 -pix_fmt rgb24 "spiffs_data\background.gif"

if %errorlevel% equ 0 (
    echo GIF created successfully: spiffs_data\background.gif
    dir spiffs_data\background.gif
    echo.
    echo Now you can build and flash:
    echo    idf.py build flash monitor
) else (
    echo GIF creation failed, please check if ffmpeg is installed
)

pause
