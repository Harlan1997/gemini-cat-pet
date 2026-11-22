$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = ".\.venv\Scripts\python.exe"
$IconPath = ".\build\app_icon.ico"
New-Item -ItemType Directory -Force -Path ".\build" | Out-Null

# Generate multi-size .ico from idle.png
& $Py -c "
from PIL import Image
im = Image.open('assets/idle.png').convert('RGBA')
w, h = im.size
side = max(w, h)
sq = Image.new('RGBA', (side, side), (0, 0, 0, 0))
sq.paste(im, ((side - w) // 2, (side - h) // 2), im)
sq.save('build/app_icon.ico', format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
"

# Build clean portable --onedir executable excluding heavy unused Qt modules
& $Py -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --onedir `
  --name "GeminiCatPet" `
  --icon "$IconPath" `
  --add-data "assets\idle.png;assets" `
  --add-data "assets\idle_half.png;assets" `
  --add-data "assets\idle_closed.png;assets" `
  --add-data "assets\idle_happy.png;assets" `
  --add-data "assets\idle_talk.png;assets" `
  --add-data "assets\nap.png;assets" `
  --add-data "assets\side_sleep.png;assets" `
  --add-data "assets\purr.png;assets" `
  --add-data "assets\groom.png;assets" `
  --add-data "assets\pounce.png;assets" `
  --add-data "assets\shy.png;assets" `
  --add-data "assets\sleepy.png;assets" `
  --add-data "assets\stretch.png;assets" `
  --add-data "assets\drag.png;assets" `
  --exclude-module PySide6.QtWebEngine `
  --exclude-module PySide6.QtWebEngineCore `
  --exclude-module PySide6.QtWebEngineWidgets `
  --exclude-module PySide6.QtPdf `
  --exclude-module PySide6.QtPdfWidgets `
  --exclude-module PySide6.Qt3DCore `
  --exclude-module PySide6.Qt3DRender `
  --exclude-module PySide6.QtQuick `
  --exclude-module PySide6.QtQml `
  --exclude-module scipy `
  main.py

$ZipPath = ".\dist\GeminiCatPet-win64.zip"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path ".\dist\GeminiCatPet" -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "Built release archive:" (Resolve-Path $ZipPath)
