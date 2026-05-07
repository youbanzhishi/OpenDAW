# VCMix Desktop Icons

Placeholder directory for application icons.

## Required icons (generate from a 1024x1024 source):

| File | Size | Format |
|------|------|--------|
| 32x32.png | 32×32 | PNG |
| 128x128.png | 128×128 | PNG |
| 128x128@2x.png | 256×256 | PNG |
| icon.icns | Multi-size | ICNS (macOS) |
| icon.ico | Multi-size | ICO (Windows) |

## Generate from source:

```bash
# Using tauri icon generator
npm run tauri icon path/to/source-icon.png

# Or manually with imagemagick
convert source.png -resize 32x32 32x32.png
convert source.png -resize 128x128 128x128.png
convert source.png -resize 256x256 128x128@2x.png
```

Until proper icons are created, Tauri will use its default icon.
