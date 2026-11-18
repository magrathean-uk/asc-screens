"""Mac App Store screenshots that look like a normal Mac screen.

A window capture is placed in the middle of a 16:10 desktop with a wallpaper,
the macOS menu bar (Apple menu, app name, menus, status icons, clock) and the
Dock (real app icons from this Mac, running-app dots, Trash). Python lays the
scene out; a small Swift/AppKit renderer draws it so fonts, SF Symbols and app
icons come from the system itself.
"""

import datetime
import json
import plistlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

# The scene is laid out in points on a 1440x900 screen and scaled to the target,
# so every accepted 16:10 Mac size gets the same composition.
LOGICAL_WIDTH = 1440
CAPTURE_SCALE = 2  # window captures from a Retina Mac: 2 pixels per point
MENUBAR_PT = 24
DOCK_TILE_PT = 52
DOCK_TILE_GAP_PT = 2
DOCK_SIDE_PAD_PT = 6
DOCK_TOP_PAD_PT = 6
DOCK_BOTTOM_PAD_PT = 10
DOCK_BOTTOM_GAP_PT = 3
DOCK_SEPARATOR_SLOT_PT = 14
DOCK_DOT_PT = 4
WINDOW_GAP_PT = 22
WINDOW_SIDE_PT = 80
WINDOW_RADIUS_PT = 16

# Framed screenshots show the desktop on a MacBook Pro M5 16-inch (Apple Frames):
# its native 3456x2234 panel at the default 1728x1117-point scaling, with the
# taller menu bar of a display with a camera notch.
MACBOOK_SCREEN = (3456, 2234)
MACBOOK_LOGICAL_WIDTH = 1728
NOTCH_MENUBAR_PT = 37

DEFAULT_MENUS = ("File", "Edit", "View", "Window", "Help")
DEFAULT_DOCK_APPS = (
    "/System/Library/CoreServices/Finder.app",
    "/Applications/Safari.app",
    "/System/Applications/Messages.app",
    "/System/Applications/Mail.app",
    "/System/Applications/Photos.app",
    "/System/Applications/Notes.app",
    "/System/Applications/App Store.app",
    "/System/Applications/System Settings.app",
)
RUNNING_BY_DEFAULT = {"Finder.app"}
TRASH = "trash"
BRIGHT_BACKGROUND = 0.6


@dataclass(frozen=True)
class MacDesktopOptions:
    app_name: str
    app_icon: Path | None
    menus: tuple[str, ...]
    clock: str
    wallpaper: Path | None
    dock_apps: tuple[str, ...]


def split_list(value):
    if not value:
        return [] if value is not None else None
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(part).strip() for part in value if str(part).strip()]


def bundle_name(bundle):
    info_path = Path(bundle) / "Contents" / "Info.plist"
    try:
        with info_path.open("rb") as handle:
            info = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return None
    name = str(info.get("CFBundleDisplayName") or info.get("CFBundleName") or "").strip()
    return name or None


def is_bundle(path):
    return Path(path).suffix.lower() == ".app"


def default_clock(today=None):
    today = today or datetime.date.today()
    return f"{today:%a} {today.day} {today:%b} 9:41"


def resolve_options(args):
    """Collect the Mac desktop settings from parsed CLI or JSON-config arguments."""
    app = getattr(args, "mac_app", None)
    app_icon = Path(app).expanduser() if app else None
    if app_icon is not None and not app_icon.exists():
        raise ValueError(f"Mac app or icon not found: {app_icon}")
    name = (getattr(args, "mac_app_name", None) or "").strip()
    if not name and app_icon is not None and is_bundle(app_icon):
        name = bundle_name(app_icon) or app_icon.stem
    if not name:
        raise ValueError("Mac desktop screenshots need --mac-app-name or a --mac-app bundle for the menu bar "
                         "(or use --mac-style fill for the old full-canvas output).")
    wallpaper = getattr(args, "mac_wallpaper", None)
    wallpaper = Path(wallpaper).expanduser() if wallpaper else None
    if wallpaper is not None and not wallpaper.is_file():
        raise ValueError(f"Mac wallpaper not found: {wallpaper}")
    menus = split_list(getattr(args, "mac_menus", None))
    dock = split_list(getattr(args, "mac_dock", None))
    missing = [entry for entry in dock or () if not Path(entry).expanduser().exists()]
    if missing:
        raise ValueError(f"Mac Dock entries not found: {', '.join(missing)}")
    return MacDesktopOptions(
        app_name=name,
        app_icon=app_icon,
        menus=tuple(DEFAULT_MENUS if menus is None else menus),
        clock=(getattr(args, "mac_clock", None) or default_clock()).strip(),
        wallpaper=wallpaper,
        dock_apps=tuple(DEFAULT_DOCK_APPS if dock is None else dock),
    )


def _path_key(path):
    path = Path(path).expanduser()
    return str(path.resolve()) if path.exists() else str(path)


def dock_entries(options, exists=Path.exists, opaque_corner=None):
    """Dock tiles in order: kept apps that exist here, the app itself (running), then Trash."""
    entries = []
    keys = []
    for value in options.dock_apps:
        path = Path(value).expanduser()
        if not exists(path) or _path_key(path) in keys:
            continue
        keys.append(_path_key(path))
        entries.append(_dock_entry(path, path.name in RUNNING_BY_DEFAULT, opaque_corner))
    if options.app_icon is not None:
        key = _path_key(options.app_icon)
        if key in keys:
            entries[keys.index(key)]["running"] = True
        else:
            entries.append(_dock_entry(options.app_icon, True, opaque_corner))
    entries.append({"source": TRASH, "kind": "trash", "mask": False, "running": False})
    return entries


def _dock_entry(path, running, opaque_corner):
    if is_bundle(path):
        # Resolve links such as /Applications/Safari.app so the icon has no alias badge.
        return {"source": str(Path(path).resolve()), "kind": "app", "mask": False, "running": running}
    # A full-bleed square icon (no transparent corners) gets the macOS icon shape.
    mask = bool(opaque_corner(path)) if opaque_corner else False
    return {"source": str(path), "kind": "image", "mask": mask, "running": running}


@dataclass(frozen=True)
class DesktopLayout:
    scale: float
    menubar_height: int
    dock_rect: tuple[float, float, float, float]
    dock_radius: float
    tiles: tuple[tuple[float, float, float, float], ...]
    separators: tuple[tuple[float, float, float, float], ...]
    window_area: tuple[float, float, float, float]


def desktop_layout(target_size, entries, logical_width=LOGICAL_WIDTH, menubar_pt=MENUBAR_PT):
    """Menu bar, Dock and the free window area, in output pixels with a top-left origin."""
    width, height = target_size
    s = width / logical_width
    menubar = round(menubar_pt * s)
    tile = DOCK_TILE_PT * s
    gap = DOCK_TILE_GAP_PT * s
    separator_count = sum(1 for entry in entries if entry["kind"] == "trash")
    dock_w = (2 * DOCK_SIDE_PAD_PT * s + len(entries) * tile + max(0, len(entries) - 1) * gap
              + separator_count * DOCK_SEPARATOR_SLOT_PT * s)
    dock_h = (DOCK_TOP_PAD_PT + DOCK_BOTTOM_PAD_PT) * s + tile
    if dock_w > width:
        raise ValueError(f"The Dock has too many apps ({len(entries)}) for a {width}-pixel screenshot; shorten --mac-dock.")
    dock_x = (width - dock_w) / 2
    dock_y = height - DOCK_BOTTOM_GAP_PT * s - dock_h
    tiles = []
    separators = []
    x = dock_x + DOCK_SIDE_PAD_PT * s
    tile_y = dock_y + DOCK_TOP_PAD_PT * s
    for index, entry in enumerate(entries):
        if entry["kind"] == "trash":
            slot = DOCK_SEPARATOR_SLOT_PT * s
            line_w = max(1.0, s)
            separators.append((x + (slot - line_w) / 2, tile_y + tile * 0.12, line_w, tile * 0.76))
            x += slot
        tiles.append((x, tile_y, tile, tile))
        x += tile + (gap if index < len(entries) - 1 else 0)
    top = menubar + WINDOW_GAP_PT * s
    bottom = dock_y - WINDOW_GAP_PT * s
    side = WINDOW_SIDE_PT * s
    return DesktopLayout(
        scale=s,
        menubar_height=menubar,
        dock_rect=(dock_x, dock_y, dock_w, dock_h),
        dock_radius=min(dock_h * 0.42, 24 * s),
        tiles=tuple(tiles),
        separators=tuple(separators),
        window_area=(side, top, width - 2 * side, bottom - top),
    )


def window_rect(layout, window_size):
    """Centre the capture in the free area at its natural size, shrinking it only to fit."""
    area_x, area_y, area_w, area_h = layout.window_area
    natural_w = window_size[0] * layout.scale / CAPTURE_SCALE
    natural_h = window_size[1] * layout.scale / CAPTURE_SCALE
    fit = min(1.0, area_w / natural_w, area_h / natural_h)
    w = round(natural_w * fit)
    h = round(natural_h * fit)
    x = round(area_x + (area_w - w) / 2)
    y = round(area_y + (area_h - h) / 2)
    return (x, y, w, h)


def build_spec(target_size, layout, entries, options, wallpaper, menubar_dark, dock_dark, jobs):
    """Everything the Swift renderer draws. jobs: [(window_path, window_rect, decorate, output_path)]."""
    s = layout.scale
    return {
        "width": target_size[0],
        "height": target_size[1],
        "scale": s,
        "wallpaper": str(wallpaper),
        "menubar": {
            "height": layout.menubar_height,
            "dark": menubar_dark,
            "app_name": options.app_name,
            "menus": list(options.menus),
            "clock": options.clock,
        },
        "dock": {
            "rect": list(layout.dock_rect),
            "radius": layout.dock_radius,
            "dark": dock_dark,
            "dot_diameter": DOCK_DOT_PT * s,
            "tiles": [
                {"rect": list(rect), **entry}
                for rect, entry in zip(layout.tiles, entries)
            ],
            "separators": [list(rect) for rect in layout.separators],
        },
        "jobs": [
            {
                "window": str(window),
                "rect": list(rect),
                "radius": WINDOW_RADIUS_PT * s,
                "decorate": decorate,
                "output": str(output),
            }
            for window, rect, decorate, output in jobs
        ],
    }


def write_renderer(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "asc_mac_desktop.swift"
    if not script.exists() or script.read_text(encoding="utf-8") != SWIFT_RENDERER:
        script.write_text(SWIFT_RENDERER, encoding="utf-8")
    return script


def render(spec, work_dir, swift_bin="swift", runner=subprocess.run):
    work_dir = Path(work_dir)
    script = write_renderer(work_dir)
    spec_path = work_dir / f"desktop-{spec['width']}x{spec['height']}.json"
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    runner([swift_bin, str(script), str(spec_path)], check=True)
    return spec_path


SWIFT_RENDERER = r'''
import AppKit
import CoreImage

struct Spec: Decodable {
    let width: Int
    let height: Int
    let scale: Double
    let wallpaper: String
    let menubar: Menubar
    let dock: Dock
    let jobs: [Job]
}
struct Menubar: Decodable { let height: Double; let dark: Bool; let appName: String; let menus: [String]; let clock: String }
struct Dock: Decodable { let rect: [Double]; let radius: Double; let dark: Bool; let dotDiameter: Double; let tiles: [Tile]; let separators: [[Double]] }
struct Tile: Decodable { let rect: [Double]; let source: String; let kind: String; let mask: Bool; let running: Bool }
struct Job: Decodable { let window: String; let rect: [Double]; let radius: Double; let decorate: Bool; let output: String }

func fail(_ message: String) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
    exit(1)
}

guard CommandLine.arguments.count == 2 else { fail("usage: asc_mac_desktop.swift SPEC.json") }
let decoder = JSONDecoder()
decoder.keyDecodingStrategy = .convertFromSnakeCase
let spec: Spec
do {
    spec = try decoder.decode(Spec.self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
} catch {
    fail("Cannot read desktop spec: \(error)")
}

let W = spec.width
let H = spec.height
let s = CGFloat(spec.scale)
let srgb = CGColorSpace(name: CGColorSpace.sRGB)!

// Spec rectangles use a top-left origin; Core Graphics uses bottom-left.
func rect(_ a: [Double]) -> CGRect {
    CGRect(x: a[0], y: Double(H) - a[1] - a[3], width: a[2], height: a[3])
}

func loadImage(_ path: String) -> CGImage {
    guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, [kCGImageSourceShouldAllowFloat: false] as CFDictionary) else {
        fail("Cannot read image: \(path)")
    }
    return image
}

func rounded(_ r: CGRect, _ radius: CGFloat) -> CGPath {
    CGPath(roundedRect: r, cornerWidth: min(radius, r.width / 2), cornerHeight: min(radius, r.height / 2), transform: nil)
}

func gray(_ white: CGFloat, _ alpha: CGFloat) -> CGColor { CGColor(gray: white, alpha: alpha) }

let wallpaper = loadImage(spec.wallpaper)
let blurredWallpaper: CGImage = {
    let input = CIImage(cgImage: wallpaper)
    let output = input.clampedToExtent().applyingGaussianBlur(sigma: Double(26 * s)).cropped(to: input.extent)
    let context = CIContext(options: [.workingColorSpace: srgb, .outputColorSpace: srgb])
    guard let image = context.createCGImage(output, from: input.extent, format: .RGBA8, colorSpace: srgb) else {
        fail("Cannot blur wallpaper")
    }
    return image
}()

func icon(for tile: Tile) -> NSImage? {
    switch tile.kind {
    case "trash":
        // The Dock's own empty-Trash artwork, as it appears in the Dock.
        return NSImage(contentsOfFile: "/System/Library/CoreServices/Dock.app/Contents/Resources/s-trashempty@2x.png")
            ?? NSImage(named: NSImage.trashEmptyName)
    case "app":
        return NSWorkspace.shared.icon(forFile: tile.source)
    default:
        return NSImage(contentsOfFile: tile.source)
    }
}

func drawText(_ text: String, font: NSFont, color: NSColor, x: CGFloat, centerY: CGFloat, shadow: NSShadow?) -> CGFloat {
    var attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: color]
    if let shadow { attributes[.shadow] = shadow }
    let string = NSAttributedString(string: text, attributes: attributes)
    let size = string.size()
    let lineHeight = ceil(font.ascender - font.descender + font.leading)
    string.draw(in: CGRect(x: x, y: centerY - lineHeight / 2, width: ceil(size.width) + 2, height: lineHeight))
    return size.width
}

func symbol(_ name: String, pointSize: CGFloat, color: NSColor) -> NSImage? {
    let config = NSImage.SymbolConfiguration(pointSize: pointSize, weight: .regular)
        .applying(NSImage.SymbolConfiguration(paletteColors: [color]))
    return NSImage(systemSymbolName: name, accessibilityDescription: nil)?.withSymbolConfiguration(config)
}

func drawSymbol(_ image: NSImage, x: CGFloat, centerY: CGFloat) {
    let size = image.size
    image.draw(in: CGRect(x: x, y: centerY - size.height / 2, width: size.width, height: size.height))
}

func drawMenubar(_ ctx: CGContext) {
    let bar = spec.menubar
    let color = bar.dark ? NSColor.white : NSColor.black
    let shadow: NSShadow? = {
        guard bar.dark else { return nil }
        let value = NSShadow()
        value.shadowColor = NSColor.black.withAlphaComponent(0.28)
        value.shadowBlurRadius = 2.5 * s
        value.shadowOffset = NSSize(width: 0, height: -0.5 * s)
        return value
    }()
    let centerY = CGFloat(H) - CGFloat(bar.height) / 2
    let regular = NSFont.systemFont(ofSize: 13 * s, weight: .regular)
    let bold = NSFont.systemFont(ofSize: 13 * s, weight: .bold)
    let shadowed: (() -> Void) -> Void = { body in
        ctx.saveGState()
        if let shadow { shadow.set() }
        body()
        ctx.restoreGState()
    }

    var x = 18 * s
    if let apple = symbol("apple.logo", pointSize: 15 * s, color: color) {
        shadowed { drawSymbol(apple, x: x, centerY: centerY + 0.5 * s) }
        x += apple.size.width + 18 * s
    }
    x += drawText(bar.appName, font: bold, color: color, x: x, centerY: centerY, shadow: shadow) + 20 * s
    for menu in bar.menus {
        x += drawText(menu, font: regular, color: color, x: x, centerY: centerY, shadow: shadow) + 20 * s
    }

    let clock = NSAttributedString(string: bar.clock, attributes: [.font: regular])
    var right = CGFloat(W) - 16 * s - ceil(clock.size().width)
    _ = drawText(bar.clock, font: regular, color: color, x: right, centerY: centerY, shadow: shadow)
    for name in ["switch.2", "magnifyingglass", "wifi"] {
        guard let image = symbol(name, pointSize: 13.5 * s, color: color) else { continue }
        right -= 19 * s + image.size.width
        shadowed { drawSymbol(image, x: right, centerY: centerY) }
    }
}

func drawDock(_ ctx: CGContext) {
    let dock = spec.dock
    let frame = rect(dock.rect)
    let path = rounded(frame, CGFloat(dock.radius))

    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -2 * s), blur: 18 * s, color: gray(0, 0.28))
    ctx.addPath(path)
    ctx.setFillColor(gray(0.5, 1))
    ctx.fillPath()
    ctx.restoreGState()

    ctx.saveGState()
    ctx.addPath(path)
    ctx.clip()
    ctx.draw(blurredWallpaper, in: CGRect(x: 0, y: 0, width: W, height: H))
    ctx.setFillColor(gray(1, dock.dark ? 0.16 : 0.34))
    ctx.fill(frame)
    ctx.restoreGState()

    ctx.saveGState()
    ctx.addPath(rounded(frame.insetBy(dx: 0.5 * s, dy: 0.5 * s), CGFloat(dock.radius) - 0.5 * s))
    ctx.setStrokeColor(gray(1, dock.dark ? 0.32 : 0.55))
    ctx.setLineWidth(1 * s)
    ctx.strokePath()
    ctx.restoreGState()

    for separator in dock.separators {
        ctx.setFillColor(gray(dock.dark ? 1 : 0, dock.dark ? 0.32 : 0.22))
        ctx.fill(rect(separator))
    }

    for tile in dock.tiles {
        let box = rect(tile.rect)
        if let image = icon(for: tile) {
            ctx.saveGState()
            if tile.mask {
                let body = box.insetBy(dx: box.width * 0.0977, dy: box.height * 0.0977)
                let shape = rounded(body, body.width * 0.225)
                ctx.saveGState()
                ctx.setShadow(offset: CGSize(width: 0, height: -1 * s), blur: 3 * s, color: gray(0, 0.3))
                ctx.addPath(shape)
                ctx.setFillColor(gray(0, 1))
                ctx.fillPath()
                ctx.restoreGState()
                ctx.addPath(shape)
                ctx.clip()
                image.draw(in: body, from: .zero, operation: .sourceOver, fraction: 1)
            } else {
                image.draw(in: box, from: .zero, operation: .sourceOver, fraction: 1)
            }
            ctx.restoreGState()
        }
        if tile.running {
            let d = CGFloat(dock.dotDiameter)
            let dot = CGRect(x: box.midX - d / 2, y: box.minY - 3.5 * s - d / 2, width: d, height: d)
            ctx.setFillColor(gray(dock.dark ? 1 : 0, dock.dark ? 0.85 : 0.6))
            ctx.fillEllipse(in: dot)
        }
    }
}

func drawWindow(_ ctx: CGContext, _ job: Job) {
    let image = loadImage(job.window)
    let frame = rect(job.rect)
    guard job.decorate else {
        ctx.draw(image, in: frame)
        return
    }
    let radius = CGFloat(job.radius)
    let shape = rounded(frame, radius)
    for (offset, blur, alpha) in [(-22 * s, 60 * s, 0.42), (-2 * s, 6 * s, 0.3)] as [(CGFloat, CGFloat, CGFloat)] {
        ctx.saveGState()
        ctx.setShadow(offset: CGSize(width: 0, height: offset), blur: blur, color: gray(0, alpha))
        ctx.addPath(shape)
        ctx.setFillColor(gray(0, 1))
        ctx.fillPath()
        ctx.restoreGState()
    }
    ctx.saveGState()
    ctx.addPath(shape)
    ctx.clip()
    ctx.draw(image, in: frame)
    ctx.restoreGState()
    ctx.saveGState()
    ctx.addPath(rounded(frame.insetBy(dx: 0.5 * s, dy: 0.5 * s), radius - 0.5 * s))
    ctx.setStrokeColor(gray(1, 0.12))
    ctx.setLineWidth(1 * s)
    ctx.strokePath()
    ctx.addPath(rounded(frame.insetBy(dx: -0.5 * s, dy: -0.5 * s), radius + 0.5 * s))
    ctx.setStrokeColor(gray(0, 0.35))
    ctx.strokePath()
    ctx.restoreGState()
}

for job in spec.jobs {
    guard let ctx = CGContext(data: nil, width: W, height: H, bitsPerComponent: 8, bytesPerRow: 0, space: srgb,
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { fail("Cannot create canvas") }
    ctx.interpolationQuality = .high
    NSGraphicsContext.current = NSGraphicsContext(cgContext: ctx, flipped: false)
    ctx.draw(wallpaper, in: CGRect(x: 0, y: 0, width: W, height: H))
    drawWindow(ctx, job)
    drawDock(ctx)
    drawMenubar(ctx)
    NSGraphicsContext.current = nil
    guard let output = ctx.makeImage(),
          let destination = CGImageDestinationCreateWithURL(URL(fileURLWithPath: job.output) as CFURL, "public.png" as CFString, 1, nil) else {
        fail("Cannot write \(job.output)")
    }
    CGImageDestinationAddImage(destination, output, nil)
    guard CGImageDestinationFinalize(destination) else { fail("Cannot write \(job.output)") }
}
'''
