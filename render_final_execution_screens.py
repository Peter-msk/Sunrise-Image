"""Generate pixel-accurate final execution screenshots of Sunrise Image.

Verifies:
1. Unbroken edge-to-edge lines on all QComboBox/QSpinBox dividers and table borders (zero mid-line breaks).
2. Exact vertical & horizontal text alignment inside all dropdowns, spinboxes, and inputs.
3. Unified 4-column grid alignment across Cards 02, 03, and 04 for maximum layout space efficiency.
"""
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


def f_reg(size):
    return ImageFont.truetype(FONT_REG, size)


def f_bold(size):
    return ImageFont.truetype(FONT_BOLD, size)


def draw_rounded_rect(draw, box, radius, fill=None, outline=None, width=1):
    if radius <= 0:
        draw.rectangle(box, fill=fill, outline=outline, width=width)
    else:
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_vcentered_text(draw, x, y, h, text, font, fill):
    """Draw left-aligned text at x, mathematically centered vertically within [y, y + h]."""
    bbox = draw.textbbox((0, 0), text, font=font)
    th = bbox[3] - bbox[1]
    ty = y + (h - th) // 2 - bbox[1]
    draw.text((x, ty), text, font=font, fill=fill)


def draw_centered_text(draw, box, text, font, fill):
    """Draw horizontally and vertically centered text within box=(x1, y1, x2, y2)."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    cx = box[0] + (box[2] - box[0] - tw) // 2 - bbox[0]
    cy = box[1] + (box[3] - box[1] - th) // 2 - bbox[1]
    draw.text((cx, cy), text, font=font, fill=fill)


def draw_pill(draw, x, y, text, bg, fg, border=None, font_size=10, pad_x=8, h_fixed=20):
    ft = f_bold(font_size)
    bbox = draw.textbbox((0, 0), text, font=ft)
    tw = bbox[2] - bbox[0]
    w = tw + pad_x * 2
    draw_rounded_rect(draw, (x, y, x + w, y + h_fixed), radius=6, fill=bg, outline=border, width=1)
    draw_centered_text(draw, (x, y, x + w, y + h_fixed), text, ft, fg)
    return w, h_fixed


def draw_button(draw, x, y, text, bg="#F1F5F9", fg="#0F172A", border="#94A3B8", font_size=11, pad_x=10, w_fixed=None, h_fixed=26, radius=6):
    ft = f_bold(font_size)
    bbox = draw.textbbox((0, 0), text, font=ft)
    tw = bbox[2] - bbox[0]
    w = w_fixed if w_fixed else (tw + pad_x * 2)
    h = h_fixed
    draw_rounded_rect(draw, (x, y, x + w, y + h), radius=radius, fill=bg, outline=border, width=1)
    draw_centered_text(draw, (x, y, x + w, y + h), text, ft, fg)
    return w, h


def draw_combo(draw, x, y, w, text, bg="#FFFFFF", fg="#0F172A", border="#94A3B8", h=26, focused=False, dark=False):
    """Draw QComboBox with 100% continuous 4-sided rounded border, edge-to-edge inner divider, and centered text."""
    bd = "#4F46E5" if focused else border
    div_c = "#282E42" if dark else "#CBD5E1"
    draw_rounded_rect(draw, (x, y, x + w, y + h), radius=6, fill=bg, outline=bd, width=1)
    # Seamless edge-to-edge inner divider (touches top inner border y+1 and bottom inner border y+h-1)
    div_x = x + w - 24
    draw.line([(div_x, y + 1), (div_x, y + h - 1)], fill=div_c, width=1)
    draw_vcentered_text(draw, x + 10, y, h, text, f_reg(11), fg)
    cx = x + w - 12
    cy = y + h // 2
    draw.polygon([(cx - 4, cy - 2), (cx + 4, cy - 2), (cx, cy + 3)], fill="#6366F1")


def draw_spin(draw, x, y, w, text, enabled=True, dark=False, h=26):
    """Draw QSpinBox with 100% continuous 4-sided rounded border, seamless T-junction dividers, and centered text."""
    bg = ("#151821" if not enabled else "#10131C") if dark else ("#F1F5F9" if not enabled else "#FFFFFF")
    fg = ("#64748B" if not enabled else "#F4F4F5") if dark else ("#94A3B8" if not enabled else "#0F172A")
    border = ("#232736" if not enabled else "#38415C") if dark else ("#CBD5E1" if not enabled else "#94A3B8")
    div_c = "#282E42" if dark else "#CBD5E1"
    draw_rounded_rect(draw, (x, y, x + w, y + h), radius=6, fill=bg, outline=border, width=1)
    bx = x + w - 21
    # Seamless vertical divider from y+1 to y+h-1 and horizontal divider from bx to x+w-1
    draw.line([(bx, y + 1), (bx, y + h - 1)], fill=div_c, width=1)
    draw.line([(bx, y + h // 2), (x + w - 1, y + h // 2)], fill=div_c, width=1)
    draw_vcentered_text(draw, x + 10, y, h, text, f_reg(11), fg)
    tri_c = "#6366F1" if enabled else ("#475569" if dark else "#94A3B8")
    draw.polygon([(bx + 7, y + 8), (bx + 13, y + 8), (bx + 10, y + 4)], fill=tri_c)
    draw.polygon([(bx + 7, y + h - 8), (bx + 13, y + h - 8), (bx + 10, y + h - 4)], fill=tri_c)


def draw_checkbox(draw, x, y, h, text, checked=False, enabled=True, dark=False, box_s=15):
    """Draw QCheckBox vertically centered within row height h."""
    by = y + (h - box_s) // 2
    if checked:
        bg = "#4F46E5" if enabled else "#94A3B8"
        bd = "#4338CA" if enabled else "#94A3B8"
    else:
        bg = ("#10131C" if dark else "#FFFFFF") if enabled else ("#151821" if dark else "#F1F5F9")
        bd = ("#64748B" if dark else "#64748B") if enabled else ("#232736" if dark else "#CBD5E1")
    draw_rounded_rect(draw, (x, by, x + box_s, by + box_s), radius=3 if box_s <= 13 else 4, fill=bg, outline=bd, width=1)
    if checked:
        draw.line([(x + 3, by + box_s // 2), (x + box_s // 2 - 1, by + box_s - 3)], fill="#FFFFFF", width=2)
        draw.line([(x + box_s // 2 - 1, by + box_s - 3), (x + box_s - 3, by + 3)], fill="#FFFFFF", width=2)
    fg = (("#F4F4F5" if dark else "#0F172A") if enabled else ("#64748B" if dark else "#94A3B8"))
    gap = 8 if box_s <= 13 else 7
    draw_vcentered_text(draw, x + box_s + gap, y, h, text, f_reg(11), fg)


def render_main_window(out_path, dark=False, completed=False):
    W, H = 1200, 760
    bg_win = "#0F1117" if dark else "#F1F5F9"
    card_bg = "#161923" if dark else "#FFFFFF"
    card_bd = "#282E42" if dark else "#CBD5E1"
    row_bd = "#1E2436" if dark else "#E2E8F0"
    fg_main = "#F4F4F5" if dark else "#0F172A"
    fg_sub = "#E4E4E7" if dark else "#1E293B"
    fg_muted = "#94A3B8" if dark else "#475569"

    im = Image.new("RGB", (W, H), bg_win)
    draw = ImageDraw.Draw(im)

    # GROUP 1: Header Card (#headerCard)
    hy = 8
    draw_rounded_rect(draw, (12, hy, W - 12, hy + 62), radius=10, fill="#1B1728", outline="#312E52", width=1)
    draw_rounded_rect(draw, (24, hy + 7, 48, hy + 31), radius=6, fill="#4F46E5")
    draw.rectangle((31, hy + 12, 41, hy + 22), fill="#FDBA74")
    draw_vcentered_text(draw, 54, hy + 6, 26, "Sunrise Image", f_bold(16), "#FFFFFF")
    draw_vcentered_text(draw, 174, hy + 6, 26, "  ·  문서 이미지 선별 추출 · 한글 본문 자르기 · 문서 내 직접 경량화", f_reg(11), "#E2E8F0")

    draw_button(draw, W - 216, hy + 7, "라이트 테마" if dark else "다크 테마", bg="#2B2138", fg="#FDE68A", border="#684D7D", w_fixed=84, h_fixed=23, font_size=10, radius=10)
    draw_pill(draw, W - 124, hy + 7, "Document / Image", bg="#2A213D", fg="#FED7AA", border="#8C5C36", font_size=10, pad_x=8, h_fixed=23)

    py = hy + 34
    draw_vcentered_text(draw, 24, py, 22, "빠른 프리셋", f_bold(11), "#FDE68A")
    presets = [("보고서·사진 JPG", not completed), ("문서 용량 줄이기", completed), ("한글 본문 자르기 PNG", False), ("인쇄용 300 DPI", False), ("원본 그대로 추출", False)]
    px_pos = 96
    for ptxt, act in presets:
        bg_p = "#5C341E" if act else "#251D36"
        bd_p = "#F97316" if act else "#473A63"
        fg_p = "#FFFFFF" if act else "#F1F5F9"
        w_p, _ = draw_button(draw, px_pos, py, ptxt, bg=bg_p, fg=fg_p, border=bd_p, font_size=10, pad_x=10, h_fixed=22, radius=10)
        px_pos += w_p + 6

    draw.rectangle((14, hy + 59, W - 14, hy + 61), fill="#F97316")

    # GROUP 2: Left Column — 01 문서 목록 (#docListCard, #docTable, width=420px)
    lx, ly, lw, lh = 12, 78, 420, 672
    draw_rounded_rect(draw, (lx, ly, lx + lw, ly + lh), radius=9, fill=card_bg, outline=card_bd, width=1)
    draw_pill(draw, lx + 12, ly + 8, "01", bg=("#431407" if dark else "#FFEDD5"), fg=("#FED7AA" if dark else "#9A3412"), border=("#9A3412" if dark else "#FDBA74"), font_size=10, pad_x=8, h_fixed=20)
    draw_vcentered_text(draw, lx + 44, ly + 8, 20, "문서 목록", f_bold(13), fg_main)
    draw_pill(draw, lx + lw - 74, ly + 8, "문서 4개", bg=("#431407" if dark else "#FFEDD5"), fg=("#FED7AA" if dark else "#9A3412"), border=("#9A3412" if dark else "#FDBA74"), font_size=10, pad_x=9, h_fixed=20)

    btn_w = (lw - 24 - 6) // 2
    by1 = ly + 34
    draw_button(draw, lx + 12, by1, "+ 문서 추가", bg=("#1E1B4B" if dark else "#EEF2FF"), fg=("#C7D2FE" if dark else "#312E81"), border=("#4338CA" if dark else "#6366F1"), w_fixed=btn_w, h_fixed=25)
    draw_button(draw, lx + 12 + btn_w + 6, by1, "+ 폴더 추가", bg=("#1E1B4B" if dark else "#EEF2FF"), fg=("#C7D2FE" if dark else "#312E81"), border=("#4338CA" if dark else "#6366F1"), w_fixed=btn_w, h_fixed=25)

    by2 = by1 + 30
    draw_button(draw, lx + 12, by2, "선택 제거", bg=("#212636" if dark else "#F1F5F9"), fg=fg_main, border=("#363E57" if dark else "#94A3B8"), w_fixed=btn_w, h_fixed=25)
    draw_button(draw, lx + 12 + btn_w + 6, by2, "전체 비우기", bg=("#212636" if dark else "#F1F5F9"), fg=fg_main, border=("#363E57" if dark else "#94A3B8"), w_fixed=btn_w, h_fixed=25)

    by3 = by2 + 30
    draw_vcentered_text(draw, lx + 12, by3, 23, "이미지 선택:", f_bold(10), fg_sub)
    chip_inact_bg = "#1E1B4B" if dark else "#EEF2FF"
    chip_inact_fg = "#C7D2FE" if dark else "#312E81"
    chip_inact_bd = "#4338CA" if dark else "#6366F1"
    draw_button(draw, lx + 78, by3, "전체", bg=chip_inact_bg, fg=chip_inact_fg, border=chip_inact_bd, w_fixed=44, h_fixed=23, font_size=10, radius=5)
    draw_button(draw, lx + 126, by3, "PNG·BMP만", bg="#4F46E5", fg="#FFFFFF", border="#3730A3", w_fixed=76, h_fixed=23, font_size=10, radius=5)
    draw_button(draw, lx + 206, by3, "1MB↑", bg=chip_inact_bg, fg=chip_inact_fg, border=chip_inact_bd, w_fixed=50, h_fixed=23, font_size=10, radius=5)
    draw_button(draw, lx + 260, by3, "500KB↑", bg=chip_inact_bg, fg=chip_inact_fg, border=chip_inact_bd, w_fixed=58, h_fixed=23, font_size=10, radius=5)
    draw_button(draw, lx + lw - 74, by3, "개별선택", bg=chip_inact_bg, fg=chip_inact_fg, border=chip_inact_bd, w_fixed=62, h_fixed=23, font_size=10, radius=5)

    tx, ty, tw, th = lx + 12, by3 + 28, lw - 24, lh - (by3 + 28 - ly) - 26
    t_bg = "#10131C" if dark else "#FFFFFF"
    t_hdr = "#1A1F2E" if dark else "#F1F5F9"
    draw_rounded_rect(draw, (tx, ty, tx + tw, ty + th), radius=7, fill=t_bg, outline=card_bd, width=1)
    draw_rounded_rect(draw, (tx + 1, ty + 1, tx + tw - 1, ty + 28), radius=6, fill=t_hdr)
    draw.rectangle((tx + 1, ty + 20, tx + tw - 1, ty + 28), fill=t_hdr)
    draw.line([(tx + 1, ty + 28), (tx + tw - 1, ty + 28)], fill=card_bd, width=1)

    c0_w, c1_w, c2_w = 194, 130, tw - 194 - 130
    draw.line([(tx + c0_w, ty + 1), (tx + c0_w, ty + 28)], fill=row_bd, width=1)
    draw.line([(tx + c0_w + c1_w, ty + 1), (tx + c0_w + c1_w, ty + 28)], fill=row_bd, width=1)
    draw_centered_text(draw, (tx, ty, tx + c0_w, ty + 28), "문서명", font=f_bold(11), fill=fg_sub)
    draw_centered_text(draw, (tx + c0_w, ty, tx + c0_w + c1_w, ty + 28), "이미지 · 용량", font=f_bold(11), fill=fg_sub)
    draw_centered_text(draw, (tx + c0_w + c1_w, ty, tx + tw, ty + 28), "비고", font=f_bold(11), fill=fg_sub)

    docs = [
        ("12142_수리수문_가. 현황, 나. 환경...", "24/75개 (-84%)" if completed else "24/75개 (120MB)", True),
        ("12142_수리수문_다. 환경평가(42...", "4/28개 (-82%)" if completed else "4/28개 (133MB)", False),
        ("12142_수리수문_라. 환경보전대...", "35/189개 (-85%)" if completed else "35/189개 (168MB)", False),
        ("12142_수리수문_라. 환경보전대...", "22/633개 (-86%)" if completed else "22/633개 (244MB)", False),
    ]
    ry = ty + 29
    for idx, (dname, dcnt, sel) in enumerate(docs):
        rh = 32
        if sel:
            draw.rectangle((tx + 1, ry, tx + tw - 1, ry + rh), fill=("#1E1B4B" if dark else "#E0E7FF"))
        elif idx % 2 == 1:
            draw.rectangle((tx + 1, ry, tx + tw - 1, ry + rh), fill=("#151925" if dark else "#F8FAFC"))
        fg_r = ("#C7D2FE" if dark else "#1E1B4B") if sel else fg_main
        draw_vcentered_text(draw, tx + 10, ry, rh, dname, f_bold(11) if sel else f_reg(11), fg_r)
        draw_centered_text(draw, (tx + c0_w, ry, tx + c0_w + c1_w, ry + rh), dcnt, font=f_reg(10), fill=fg_r)
        btn_w_pre = 58
        btn_x_pre = tx + c0_w + c1_w + (c2_w - btn_w_pre) // 2
        draw_button(
            draw, btn_x_pre, ry + 5, "미리보기",
            bg=("#1E1B4B" if dark else "#EEF2FF"),
            fg=("#C7D2FE" if dark else "#312E81"),
            border=("#4338CA" if dark else "#6366F1"),
            font_size=10, pad_x=6, h_fixed=22, w_fixed=btn_w_pre, radius=5,
        )
        draw.line([(tx + 1, ry + rh), (tx + tw - 1, ry + rh)], fill=row_bd, width=1)
        ry += rh

    draw_vcentered_text(draw, lx + 12, ly + lh - 22, 18, "상단 [PNG·BMP만 · 1MB↑] 또는 [미리보기]로 원하는 이미지만 선별 변환", f_reg(10), fg_muted)

    # GROUPS 4, 5, 6, 7: Right Column with Unified 4-Column Grid Alignment
    rx, rw = 442, W - 442 - 12  # rw = 746
    # Unified X-coordinates across Card 02, Card 03, Card 04:
    # Col 0 label: rx + 12 (width 92)
    # Col 1 input: rx + 108 (width 256 -> ends at rx + 364)
    # Col 2 label: rx + 378 (width 72)
    # Col 3 input: rx + 454 (width 280 -> ends at rx + 734 = rx + rw - 12!)
    c0_x = rx + 12
    c1_x, c1_w = rx + 108, 256
    c2_x = rx + 378
    c3_x, c3_w = rx + 454, rw - 12 - 454  # 280px

    ry_pos = 78

    # GROUP 4: Card 02 (#formatCard)
    c2_h = 168
    draw_rounded_rect(draw, (rx, ry_pos, rx + rw, ry_pos + c2_h), radius=9, fill=card_bg, outline=card_bd, width=1)
    draw_pill(draw, c0_x, ry_pos + 8, "02", bg=("#1E1B4B" if dark else "#EEF2FF"), fg=("#C7D2FE" if dark else "#312E81"), border=("#4338CA" if dark else "#6366F1"), font_size=10, pad_x=8, h_fixed=20)
    draw_vcentered_text(draw, rx + 44, ry_pos + 8, 20, "저장 형식과 이미지 처리", f_bold(13), fg_main)

    draw_vcentered_text(draw, rx + rw - 412, ry_pos + 6, 24, "변환 대상", f_bold(11), fg_sub)
    draw_combo(draw, rx + rw - 354, ry_pos + 6, 246, "PNG · BMP 무손실 이미지만 변환", bg=("#10131C" if dark else "#FFFFFF"), fg=fg_main, border=("#38415C" if dark else "#94A3B8"), h=24, dark=dark)
    draw_button(draw, rx + rw - 102, ry_pos + 6, "목록에서 선택…", bg=chip_inact_bg, fg=chip_inact_fg, border=chip_inact_bd, w_fixed=90, h_fixed=24, font_size=10, radius=5)

    g1 = ry_pos + 35
    draw_vcentered_text(draw, c0_x, g1, 26, "저장 형식", f_bold(11), fg_sub)
    draw_combo(draw, c1_x, g1, c1_w, "JPG · 사진 / 보고서 (권장)", bg=("#10131C" if dark else "#FFFFFF"), fg=fg_main, border=("#38415C" if dark else "#94A3B8"), focused=True, dark=dark)
    draw_vcentered_text(draw, c2_x, g1, 26, "투명 배경", f_bold(11), fg_sub)
    draw_combo(draw, c3_x, g1, c3_w, "가능한 형식에서 투명 유지", bg=("#10131C" if dark else "#FFFFFF"), fg=fg_main, border=("#38415C" if dark else "#94A3B8"), dark=dark)

    g2 = ry_pos + 67
    draw_vcentered_text(draw, c0_x, g2, 26, "회전 / 파일명", f_bold(11), fg_sub)
    draw_combo(draw, c1_x, g2, 108, "회전 안 함", bg=("#10131C" if dark else "#FFFFFF"), fg=fg_main, border=("#38415C" if dark else "#94A3B8"), dark=dark)
    draw_combo(draw, c1_x + 114, g2, c1_w - 114, "순번_원본명", bg=("#10131C" if dark else "#FFFFFF"), fg=fg_main, border=("#38415C" if dark else "#94A3B8"), dark=dark)
    draw_checkbox(draw, c2_x, g2, 26, "한글 본문 자르기 반영 (HWPX)", checked=False, enabled=True, dark=dark)
    draw_checkbox(draw, c3_x + 132, g2, 26, "흑백(회색조) 저장", checked=False, enabled=True, dark=dark)

    g3 = ry_pos + 99
    draw_vcentered_text(draw, c0_x, g3, 26, "저장 위치", f_bold(11), fg_sub)
    dest_w = (c3_x + c3_w) - c1_x - 156
    draw_rounded_rect(draw, (c1_x, g3, c1_x + dest_w, g3 + 26), radius=6, fill=("#10131C" if dark else "#FFFFFF"), outline=("#38415C" if dark else "#94A3B8"), width=1)
    draw_vcentered_text(draw, c1_x + 10, g3, 26, "F:\\스캔파일", f_reg(11), fg_main)
    draw_button(draw, c1_x + dest_w + 6, g3, "폴더 선택", bg=("#212636" if dark else "#F1F5F9"), fg=fg_main, border=("#363E57" if dark else "#94A3B8"), w_fixed=72, h_fixed=26)
    draw_button(draw, c1_x + dest_w + 84, g3, "폴더 열기", bg=("#212636" if dark else "#F1F5F9"), fg=fg_main, border=("#363E57" if dark else "#94A3B8"), w_fixed=72, h_fixed=26)

    draw_rounded_rect(draw, (c0_x, ry_pos + 132, rx + rw - 12, ry_pos + 158), radius=6, fill=("#181C28" if dark else "#F8FAFC"), outline=card_bd, width=1)
    draw_vcentered_text(draw, c0_x + 10, ry_pos + 132, 26, "JPG는 손실 압축 · 투명 배경은 흰색 또는 검정으로 처리합니다. (문서 경량화 시 투명 직인은 PNG 자동 유지)", f_reg(10), fg_muted)

    # GROUP 5: Card 03 (#sizeCard — aligned on exact same c0_x, c1_x, c2_x, c3_x!)
    c3_y = 254
    c3_h = 124
    draw_rounded_rect(draw, (rx, c3_y, rx + rw, c3_y + c3_h), radius=9, fill=card_bg, outline=card_bd, width=1)
    draw_pill(draw, c0_x, c3_y + 8, "03", bg=("#2E1065" if dark else "#F3E8FF"), fg=("#E9D5FF" if dark else "#5B21B6"), border=("#6D28D9" if dark else "#C4B5FD"), font_size=10, pad_x=8, h_fixed=20)
    draw_vcentered_text(draw, rx + 44, c3_y + 8, 20, "해상도와 인쇄 DPI", f_bold(13), fg_main)

    z1 = c3_y + 34
    draw_vcentered_text(draw, c0_x, z1, 26, "해상도", f_bold(11), fg_sub)
    draw_combo(draw, c1_x, z1, c1_w, "원본 픽셀 유지", bg=("#10131C" if dark else "#FFFFFF"), fg=fg_main, border=("#38415C" if dark else "#94A3B8"), dark=dark)
    draw_vcentered_text(draw, c2_x, z1, 26, "크기 비율", f_bold(11), fg_sub)
    draw_spin(draw, c3_x, z1, 104, "100 %", enabled=False, dark=dark)
    draw_checkbox(draw, c3_x + 114, z1, 26, "원본보다 크게 확대 허용", checked=False, enabled=False, dark=dark)

    z2 = c3_y + 66
    draw_vcentered_text(draw, c0_x, z2, 26, "가로 / 세로", f_bold(11), fg_sub)
    w_spin = (c1_w - 22) // 2
    draw_spin(draw, c1_x, z2, w_spin, "1920 px", enabled=False, dark=dark)
    draw_centered_text(draw, (c1_x + w_spin, z2, c1_x + w_spin + 22, z2 + 26), "×", f_bold(12), fg_muted)
    draw_spin(draw, c1_x + w_spin + 22, z2, w_spin, "1080 px", enabled=False, dark=dark)
    draw_vcentered_text(draw, c2_x, z2, 26, "인쇄 밀도", f_bold(11), fg_sub)
    draw_checkbox(draw, c3_x, z2, 26, "DPI 지정", checked=True, enabled=True, dark=dark)
    draw_spin(draw, c3_x + 92, z2, 108, "300 dpi", enabled=True, dark=dark)

    draw_vcentered_text(draw, c0_x, c3_y + 98, 20, "비율 유지 · DPI만 바꾸면 픽셀 수는 그대로입니다. 미지정 시 저장 가능한 형식에 원본 DPI를 유지합니다.", f_reg(10), fg_muted)

    # GROUP 6: Card 04 (#capacityCard — aligned on exact same c0_x, c1_x, c2_x, c3_x!)
    c4_y = 386
    c4_h = 124
    draw_rounded_rect(draw, (rx, c4_y, rx + rw, c4_y + c4_h), radius=9, fill=card_bg, outline=card_bd, width=1)
    draw_pill(draw, c0_x, c4_y + 8, "04", bg=("#042F2E" if dark else "#CCFBF1"), fg=("#99F6E4" if dark else "#115E59"), border=("#0F766E" if dark else "#5EEAD4"), font_size=10, pad_x=8, h_fixed=20)
    draw_vcentered_text(draw, rx + 44, c4_y + 8, 20, "품질과 목표 용량", f_bold(13), fg_main)

    q1 = c4_y + 34
    draw_vcentered_text(draw, c0_x, q1, 26, "JPG / WebP 품질", f_bold(11), fg_sub)
    draw_spin(draw, c1_x, q1, 92, "85" if completed else "95", enabled=True, dark=dark)
    draw_checkbox(draw, c1_x + 102, q1, 26, "WebP 무손실 압축", checked=False, enabled=False, dark=dark)
    draw_vcentered_text(draw, c2_x, q1, 26, "PNG 압축", f_bold(11), fg_sub)
    draw_spin(draw, c3_x, q1, 92, "6", enabled=False, dark=dark)
    draw_vcentered_text(draw, c3_x + 102, q1, 26, "단계 (0~9)", f_reg(10), fg_muted)

    q2 = c4_y + 66
    draw_vcentered_text(draw, c0_x, q2, 26, "목표 최대 용량", f_bold(11), fg_sub)
    draw_checkbox(draw, c1_x, q2, 26, "이미지 한 장당", checked=True, enabled=True, dark=dark)
    draw_spin(draw, c1_x + 102, q2, 82, "300", enabled=True, dark=dark)
    draw_combo(draw, c1_x + 188, q2, c1_w - 188, "KB", bg=("#10131C" if dark else "#FFFFFF"), fg=fg_main, border=("#38415C" if dark else "#94A3B8"), dark=dark)
    draw_vcentered_text(draw, c2_x, q2, 26, "초과 시 처리", f_bold(11), fg_sub)
    draw_checkbox(draw, c3_x, q2, 26, "용량이 초과하면 픽셀 크기도 추가 축소", checked=True, enabled=True, dark=dark)

    draw_vcentered_text(draw, c0_x, c4_y + 98, 20, "KB(킬로바이트) · MB(메가바이트) 단위로 이미지 최대 용량을 지정할 수 있습니다. (1 MB = 1,024 KB)", f_reg(10), fg_muted)

    # GROUP 7: Summary Pill Banner, Progress Panel & Action Footer
    s_y = 518
    draw_rounded_rect(draw, (rx, s_y, rx + rw, s_y + 28), radius=7, fill=("#1E1B4B" if dark else "#EEF2FF"), outline=("#4338CA" if dark else "#6366F1"), width=1)
    draw_vcentered_text(draw, c0_x, s_y, 28, "JPEG  /  원본 픽셀 유지  /  300 DPI  /  한 장당 300.0 KB 이하 목표  /  대상: PNG·BMP 무손실 이미지", f_bold(11), ("#C7D2FE" if dark else "#312E81"))

    p_y = 554
    p_h = 132
    draw_rounded_rect(draw, (rx, p_y, rx + rw, p_y + p_h), radius=9, fill=card_bg, outline=card_bd, width=1)
    draw_vcentered_text(draw, c0_x, p_y + 8, 20, "현재 문서: 12142_수리수문_라. 환경보전대책(국가하천).hwpx", f_bold(11), fg_main)
    draw_vcentered_text(draw, rx + rw - 178, p_y + 8, 20, "문서 4개 · 선택 이미지 85개", f_reg(10), fg_muted)

    draw_vcentered_text(draw, c0_x, p_y + 30, 20, "최근 이미지: image009.bmp → JPG 변환 (218.5 KB)", f_reg(10), fg_muted)
    draw_vcentered_text(draw, rx + rw - 318, p_y + 30, 20, "✓ 변환 대상 [PNG·BMP 무손실 이미지]: 선택 85 / 전체 925개", f_bold(10), ("#99F6E4" if dark else "#0D9488"))

    pb_y = p_y + 56
    pb_w = (rw - 30) // 2
    draw_rounded_rect(draw, (c0_x, pb_y, c0_x + pb_w, pb_y + 24), radius=6, fill=("#22283A" if dark else "#E2E8F0"), outline=card_bd, width=1)
    pct1 = 1.0 if completed else 0.783
    draw_rounded_rect(draw, (c0_x + 1, pb_y + 1, c0_x + 1 + int((pb_w - 2) * pct1), pb_y + 23), radius=5, fill="#6366F1")
    txt_bar1 = "전체 100.0% · 완료 85/85개" if completed else "전체 78.3% · 처리 67/85개"
    draw_centered_text(draw, (c0_x, pb_y, c0_x + pb_w, pb_y + 24), txt_bar1, font=f_bold(10), fill="#FFFFFF")

    draw_rounded_rect(draw, (c0_x + pb_w + 6, pb_y, c0_x + pb_w * 2 + 6, pb_y + 24), radius=6, fill=("#22283A" if dark else "#E2E8F0"), outline=card_bd, width=1)
    pct2 = 1.0 if completed else 0.850
    draw_rounded_rect(draw, (c0_x + pb_w + 7, pb_y + 1, c0_x + pb_w + 7 + int((pb_w - 2) * pct2), pb_y + 23), radius=5, fill="#F97316")
    txt_bar2 = "현재 문서 100.0% · 완료 22개" if completed else "현재 문서 85.0% · 남음 3개"
    draw_centered_text(draw, (c0_x + pb_w + 6, pb_y, c0_x + pb_w * 2 + 6, pb_y + 24), txt_bar2, font=f_bold(10), fill="#FFFFFF")

    sub_txt = "선택 이미지 문서 경량화 완료 · 변환 85개 (665.00 MB → 98.40 MB, -85.2%) / 주의 0개 / 실패 0개" if completed else "메인 실행창에서 선택된 PNG·BMP 무손실 이미지 85개만 고속 변환 중 (미선택 이미지는 원본 유지)"
    draw_vcentered_text(draw, c0_x, p_y + 94, 22, sub_txt, f_reg(10), fg_muted)

    a_y = 694
    draw_button(draw, rx, a_y, "결과 폴더 열기", bg=("#212636" if dark else "#F1F5F9"), fg=fg_main, border=("#363E57" if dark else "#94A3B8"), w_fixed=98, h_fixed=28, radius=7)
    draw_button(draw, rx + 104, a_y, "설정 초기화", bg=("#212636" if dark else "#F1F5F9"), fg=fg_main, border=("#363E57" if dark else "#94A3B8"), w_fixed=88, h_fixed=28, radius=7)
    draw_button(draw, rx + 198, a_y, "처리 기록 보기", bg=("#212636" if dark else "#F1F5F9"), fg=fg_main, border=("#363E57" if dark else "#94A3B8"), w_fixed=98, h_fixed=28, radius=7)

    draw_button(draw, rx + rw - 368, a_y, "중지", bg="#FFF1F2", fg="#BE123C", border="#F43F5E", w_fixed=54, h_fixed=28, radius=7)
    draw_button(draw, rx + rw - 308, a_y, "선택 이미지 문서 내 변환", bg="#0D9488", fg="#FFFFFF", border="#0F766E", w_fixed=158, h_fixed=28, radius=7)
    draw_button(draw, rx + rw - 144, a_y, "선택 이미지 변환 추출", bg="#4F46E5", fg="#FFFFFF", border="#4338CA", w_fixed=144, h_fixed=28, radius=7)

    draw_vcentered_text(draw, rx, 730, 18, "지원 문서: 개방형 한글(.hwpx), PDF(.pdf), Excel(.xlsx), Word(.docx), PowerPoint(.pptx) · 구형 한글(.hwp)은 지원 대상에서 제외됩니다.", f_reg(10), fg_muted)
    im.save(out_path)


def render_popup_window(out_path):
    W, H = 1200, 740
    im = Image.new("RGB", (W, H), "#F1F5F9")
    draw = ImageDraw.Draw(im)

    # GROUP 8A: Top Selector & Quick Settings Bar Card (#previewTopCard)
    ty = 10
    draw_rounded_rect(draw, (12, ty, W - 12, ty + 68), radius=9, fill="#FFFFFF", outline="#CBD5E1", width=1)
    draw_rounded_rect(draw, (22, ty + 8, 42, ty + 28), radius=5, fill="#4F46E5")
    draw_pill(draw, 48, ty + 8, "문서 선택", bg="#FFEDD5", fg="#9A3412", border="#FDBA74", font_size=10, pad_x=8, h_fixed=20)
    draw_combo(draw, 124, ty + 6, 456, "01. 12142_수리수문_가. 현황, 나. 환경보전목표 (선택 24 / 75개 · 120.41 MB)", bg="#FFFFFF", fg="#0F172A", border="#94A3B8", h=26)

    draw_button(draw, 588, ty + 6, "이 이미지만 바로 추출", bg="#0D9488", fg="#FFFFFF", border="#0F766E", w_fixed=134, h_fixed=26)
    draw_button(draw, 728, ty + 6, "선택 이미지 변환 추출", bg="#4F46E5", fg="#FFFFFF", border="#4338CA", w_fixed=140, h_fixed=26)
    draw_button(draw, 874, ty + 6, "선택 이미지 문서 내 변환", bg="#2563EB", fg="#FFFFFF", border="#1D4ED8", w_fixed=154, h_fixed=26)
    draw_button(draw, 1034, ty + 6, "결과 폴더 열기", bg="#F1F5F9", fg="#0F172A", border="#94A3B8", w_fixed=96, h_fixed=26)

    r2_y = ty + 37
    draw_vcentered_text(draw, 24, r2_y, 25, "빠른 설정 연동", f_bold(11), "#1E293B")
    draw_combo(draw, 108, r2_y, 236, "JPG · 사진 / 보고서 (권장)", bg="#FFFFFF", fg="#0F172A", border="#94A3B8", h=25)
    draw_checkbox(draw, 356, r2_y, 25, "한글 본문 자르기 반영 (HWPX)", checked=False, enabled=True, dark=False)
    draw_checkbox(draw, 548, r2_y, 25, "목표 최대 용량 제한 사용", checked=True, enabled=True, dark=False)
    draw_vcentered_text(draw, 706, r2_y, 25, "JPEG / 원본 픽셀 유지 / 300 DPI / 대상: PNG·BMP 무손실 이미지", f_reg(10), "#475569")

    # Center Splitter: GROUP 8B (LIST = 568px) | GROUP 8C (VIEW = 598px)
    sy = 86
    sh = 608
    lw = 568
    rw = W - 24 - lw - 10
    lx = 12
    rx = lx + lw + 10

    # GROUP 8B: Left Card — LIST (#previewListCard, #imageTree)
    draw_rounded_rect(draw, (lx, sy, lx + lw, sy + sh), radius=9, fill="#FFFFFF", outline="#CBD5E1", width=1)
    draw_pill(draw, lx + 12, sy + 9, "LIST", bg="#EEF2FF", fg="#312E81", border="#6366F1", font_size=10, pad_x=8, h_fixed=20)
    draw_vcentered_text(draw, lx + 58, sy + 9, 20, "이미지 목록 / 체크한 항목만 변환·추출", f_bold(13), "#0F172A")
    draw_pill(draw, lx + lw - 104, sy + 9, "체크 24 / 75개", bg="#EEF2FF", fg="#312E81", border="#6366F1", font_size=10, pad_x=8, h_fixed=20)

    draw_rounded_rect(draw, (lx + 12, sy + 36, lx + lw - 84, sy + 62), radius=6, fill="#FFFFFF", outline="#94A3B8", width=1)
    draw_vcentered_text(draw, lx + 22, sy + 36, 26, "이름 · 위치 · 형식으로 찾기 (Ctrl+F)", f_reg(11), "#94A3B8")
    draw_button(draw, lx + lw - 76, sy + 36, "새로고침", bg="#F1F5F9", fg="#0F172A", border="#94A3B8", w_fixed=64, h_fixed=26)

    sby1 = sy + 68
    w4 = (lw - 24 - 18) // 4
    draw_button(draw, lx + 12, sby1, "전체 선택", bg="#F1F5F9", fg="#0F172A", border="#94A3B8", w_fixed=w4, h_fixed=25)
    draw_button(draw, lx + 12 + (w4 + 6), sby1, "전체 취소", bg="#F1F5F9", fg="#0F172A", border="#94A3B8", w_fixed=w4, h_fixed=25)
    draw_button(draw, lx + 12 + (w4 + 6)*2, sby1, "선택 반전", bg="#F1F5F9", fg="#0F172A", border="#94A3B8", w_fixed=w4, h_fixed=25)
    draw_button(draw, lx + 12 + (w4 + 6)*3, sby1, "선택 관리 ▼", bg="#F1F5F9", fg="#0F172A", border="#94A3B8", w_fixed=w4, h_fixed=25)

    sby2 = sby1 + 31
    draw_vcentered_text(draw, lx + 12, sby2, 23, "빠른 필터:", f_bold(10), "#1E293B")
    draw_button(draw, lx + 70, sby2, "1MB↑", bg="#EEF2FF", fg="#312E81", border="#6366F1", w_fixed=52, h_fixed=23, font_size=10, radius=5)
    draw_button(draw, lx + 126, sby2, "500KB↑", bg="#EEF2FF", fg="#312E81", border="#6366F1", w_fixed=60, h_fixed=23, font_size=10, radius=5)
    draw_button(draw, lx + 190, sby2, "PNG·BMP", bg="#4F46E5", fg="#FFFFFF", border="#4338CA", w_fixed=70, h_fixed=23, font_size=10, radius=5)
    draw_button(draw, lx + lw - 222, sby2, "선택 이미지만 변환", bg="#0D9488", fg="#FFFFFF", border="#0F766E", w_fixed=114, h_fixed=23, font_size=10, radius=5)
    draw_button(draw, lx + lw - 102, sby2, "선택 변환 추출", bg="#4F46E5", fg="#FFFFFF", border="#4338CA", w_fixed=90, h_fixed=23, font_size=10, radius=5)

    # 5-Column Image Tree (#imageTree) — continuous row lines, 28px+ row height, 13x13px indicator
    ttx, tty, ttw, tth = lx + 12, sby2 + 29, lw - 24, sh - (sby2 + 29 - sy) - 28
    draw_rounded_rect(draw, (ttx, tty, ttx + ttw, tty + tth), radius=7, fill="#FFFFFF", outline="#CBD5E1", width=1)
    draw_rounded_rect(draw, (ttx + 1, tty + 1, ttx + ttw - 1, tty + 28), radius=6, fill="#F1F5F9")
    draw.rectangle((ttx + 1, tty + 20, ttx + ttw - 1, tty + 28), fill="#F1F5F9")
    draw.line([(ttx + 1, tty + 28), (ttx + ttw - 1, tty + 28)], fill="#CBD5E1", width=1)

    col_bounds = [
        (ttx, ttx + 178),
        (ttx + 178, ttx + 232),
        (ttx + 232, ttx + 318),
        (ttx + 318, ttx + 424),
        (ttx + 424, ttx + ttw),
    ]
    headers = ["선택 / 이미지", "형식", "원본 용량", "해상도 px", "자르기 / 위치"]
    for idx, htxt in enumerate(headers):
        b = col_bounds[idx]
        if idx > 0:
            draw.line([(b[0], tty + 1), (b[0], tty + 28)], fill="#E2E8F0", width=1)
        draw_centered_text(draw, (b[0], tty, b[1], tty + 28), htxt, font=f_bold(10), fill="#1E293B")

    rows = [
        ("001 · image1.jpg", "JPEG", "9.43 MB", "4501 × 6221", "내장 원본", False, False),
        ("002 · image2.jpg", "JPEG", "1.78 MB", "4960 × 7015", "내장 원본", False, False),
        ("003 · image3.jpg", "JPEG", "1.36 MB", "4532 × 6710", "내장 원본", False, True),
        ("004 · image4.jpg", "JPEG", "1.84 MB", "2640 × 3649", "내장 원본", False, False),
        ("009 · image9.bmp", "BMP", "11.05 MB", "1653 × 2337", "내장 원본", True, False),
        ("010 · image10.bmp", "BMP", "24.87 MB", "2480 × 3505", "내장 원본", True, False),
        ("011 · image11.bmp", "BMP", "24.87 MB", "2480 × 3505", "내장 원본", True, False),
        ("012 · image12.bmp", "BMP", "24.87 MB", "2480 × 3505", "내장 원본", True, False),
        ("013 · image13.bmp", "BMP", "11.05 MB", "1653 × 2337", "내장 원본", True, False),
        ("014 · image14.bmp", "BMP", "11.05 MB", "1653 × 2337", "내장 원본", True, False),
        ("015 · image15.jpg", "JPEG", "1.56 MB", "4546 × 6300", "내장 원본", False, False),
    ]
    r_y = tty + 29
    for idx, (iname, ifmt, isize, ires, iloc, chk, cur) in enumerate(rows):
        rh = 30
        if cur:
            draw.rectangle((ttx + 1, r_y, ttx + ttw - 1, r_y + rh), fill="#E0E7FF")
        elif idx % 2 == 1:
            draw.rectangle((ttx + 1, r_y, ttx + ttw - 1, r_y + rh), fill="#F8FAFC")

        draw_checkbox(draw, ttx + 10, r_y, rh, iname, checked=chk, enabled=True, box_s=13)
        draw_centered_text(draw, (col_bounds[1][0], r_y, col_bounds[1][1], r_y + rh), ifmt, font=(f_bold(10) if chk else f_reg(10)), fill=("#312E81" if chk else "#0F172A"))
        draw_centered_text(draw, (col_bounds[2][0], r_y, col_bounds[2][1], r_y + rh), isize, font=f_reg(10), fill="#0F172A")
        draw_centered_text(draw, (col_bounds[3][0], r_y, col_bounds[3][1], r_y + rh), ires, font=f_reg(10), fill="#0F172A")
        draw_centered_text(draw, (col_bounds[4][0], r_y, col_bounds[4][1], r_y + rh), iloc, font=f_reg(10), fill="#475569")

        draw.line([(ttx + 1, r_y + rh), (ttx + ttw - 1, r_y + rh)], fill="#E2E8F0", width=1)
        r_y += rh

    draw_vcentered_text(draw, lx + 12, sy + sh - 22, 18, "이 문서 75개 / 체크 24개 (307.30 MB) · 전체 문서 체크 85개", f_reg(10), "#475569")

    # GROUP 8C: Right Card — VIEW 미리보기 / 원본 비교 (#previewViewCard)
    draw_rounded_rect(draw, (rx, sy, rx + rw, sy + sh), radius=9, fill="#FFFFFF", outline="#CBD5E1", width=1)
    draw_pill(draw, rx + 12, sy + 9, "VIEW", bg="#F3E8FF", fg="#5B21B6", border="#C4B5FD", font_size=10, pad_x=8, h_fixed=20)
    draw_vcentered_text(draw, rx + 62, sy + 9, 20, "미리보기 / 원본 비교", f_bold(13), "#0F172A")
    draw_vcentered_text(draw, rx + rw - 175, sy + 9, 20, "003 · image3.jpg · 내장 원본", f_reg(10), "#475569")

    vy = sy + 36
    draw_button(draw, rx + 12, vy, "◀ 이전", bg="#F1F5F9", fg="#0F172A", border="#94A3B8", w_fixed=64, h_fixed=26)
    draw_button(draw, rx + 82, vy, "다음 ▶", bg="#F1F5F9", fg="#0F172A", border="#94A3B8", w_fixed=64, h_fixed=26)
    draw_combo(draw, rx + 152, vy, 136, "변환 결과", bg="#FFFFFF", fg="#0F172A", border="#94A3B8", h=26)
    draw_button(draw, rx + 294, vy, "원본 ⇄ 결과", bg="#EEF2FF", fg="#312E81", border="#6366F1", w_fixed=94, h_fixed=26)
    draw_button(draw, rx + 394, vy, "－", bg="#F1F5F9", fg="#0F172A", border="#94A3B8", w_fixed=28, h_fixed=26)
    draw_button(draw, rx + 428, vy, "창 맞춤", bg="#F1F5F9", fg="#0F172A", border="#94A3B8", w_fixed=64, h_fixed=26)
    draw_button(draw, rx + 498, vy, "＋", bg="#F1F5F9", fg="#0F172A", border="#94A3B8", w_fixed=28, h_fixed=26)
    draw_button(draw, rx + 532, vy, "갱신", bg="#F1F5F9", fg="#0F172A", border="#94A3B8", w_fixed=54, h_fixed=26)

    px, py, pw, ph = rx + 12, sy + 70, rw - 24, sh - 134
    draw_rounded_rect(draw, (px, py, px + pw, py + ph), radius=7, fill="#FFFFFF", outline="#CBD5E1", width=1)

    # Schematic diagram preview inside VIEW
    cx, cy, cw, ch = px + 60, py + 16, pw - 120, ph - 32
    draw.line([(cx + cw // 2, cy + 10), (cx + cw // 2, cy + ch - 20)], fill="#1E293B", width=2)
    for step_y in range(cy + 30, cy + ch - 30, 48):
        draw.line([(cx + 40, step_y), (cx + cw - 40, step_y)], fill="#EF4444", width=2)
        draw.rectangle((cx + cw // 2 - 24, step_y - 10, cx + cw // 2 + 24, step_y + 10), fill="#F8FAFC", outline="#475569", width=1)

    iby = sy + sh - 56
    draw_rounded_rect(draw, (rx + 12, iby, rx + rw - 12, sy + sh - 8), radius=6, fill="#EEF2FF", outline="#6366F1", width=1)
    draw_vcentered_text(draw, rx + 22, iby + 3, 22, "원본 4532 × 6710 px / 1.36 MB  →  결과 4532 × 6710 px / 912.4 KB (-32.9%) / 300 DPI", f_bold(11), "#312E81")
    draw_vcentered_text(draw, rx + 22, iby + 24, 20, "체크박스(13×13px)와 행 높이(28px)가 분리 설계되어 행 간 겹침 없이 쾌적하게 선택할 수 있습니다.", f_reg(10), "#4338CA")

    fy = 702
    draw_vcentered_text(draw, 16, fy, 28, "✓ PNG·BMP 무손실 이미지 24개가 선택되었습니다. [선택 이미지만 변환] 또는 [선택 변환 추출]로 선택된 항목만 변환하세요.", f_bold(10), "#0D9488")
    draw_button(draw, W - 116, fy, "창 닫기 (Esc)", bg="#F1F5F9", fg="#0F172A", border="#94A3B8", w_fixed=104, h_fixed=28)

    im.save(out_path)


def render_dropdown_comparison(out_path):
    W, H = 900, 500
    im = Image.new("RGB", (W, H), "#F1F5F9")
    draw = ImageDraw.Draw(im)

    draw_rounded_rect(draw, (14, 14, W - 14, H - 14), radius=9, fill="#FFFFFF", outline="#CBD5E1", width=1)
    draw_vcentered_text(draw, 28, 22, 24, "최종 UI 마감 검증: (1) 끊김 없는 1px 라인 마감 · (2) 드롭박스 수직 중앙 정렬 · (3) 카드 02~04 그리드 통일", f_bold(14), "#0F172A")
    draw_vcentered_text(draw, 28, 46, 20, "드롭박스/스핀박스 내부 구분선 위아래 끊김 제거(margin:0px) 및 텍스트 수직 중앙 정렬(padding-y:0px)을 완료했습니다.", f_reg(11), "#475569")

    # Left: Before
    lx = 32
    draw_vcentered_text(draw, lx, 80, 22, "■ 보완 전 (구분선 상하 끊김 · 텍스트 상단 쏠림 · 체크박스 겹침)", f_bold(12), "#EF4444")
    draw_rounded_rect(draw, (lx, 112, lx + 248, 140), radius=6, fill="#FFFFFF", outline="#94A3B8", width=1)
    # Disconnected inner line (y+5 to y+23) and top-shifted text (y+2)
    draw.line([(lx + 224, 117), (lx + 224, 135)], fill="#CBD5E1", width=1)
    draw.text((lx + 10, 114), "JPG · 사진 / 보고서 (권장)", font=f_reg(11), fill="#0F172A")
    draw.polygon([(lx + 232, 124), (lx + 240, 124), (lx + 236, 129)], fill="#6366F1")
    draw_pill(draw, lx + 256, 116, "구분선 상하 끊김 & 텍스트 쏠림", bg="#FEF2F2", fg="#B91C1C", border="#EF4444", font_size=10, pad_x=8, h_fixed=20)

    draw_rounded_rect(draw, (lx, 165, lx + 380, 320), radius=6, fill="#FFFFFF", outline="#CBD5E1", width=1)
    for i in range(6):
        ry_old = 175 + i * 18
        draw_rounded_rect(draw, (lx + 10, ry_old, lx + 28, ry_old + 18), radius=3, fill="#4F46E5" if i >= 3 else "#FFFFFF", outline="#64748B", width=1)
        draw.text((lx + 29, ry_old + 1), f"00{i+1} · image{i+1}.bmp", font=f_reg(11), fill="#0F172A")
    draw_pill(draw, lx + 20, 335, "행 높이(18px) ≤ 체크박스(19px)로 상하 테두리 겹침", bg="#FEF2F2", fg="#B91C1C", border="#EF4444", font_size=10, pad_x=10, h_fixed=22)

    # Right: After
    rx = 460
    draw_vcentered_text(draw, rx, 80, 22, "■ 보완 후 (끊김 없는 Edge-to-Edge 라인 & 수직 중앙 정렬)", f_bold(12), "#10B981")
    draw_combo(draw, rx, 112, 248, "JPG · 사진 / 보고서 (권장)", bg="#FFFFFF", fg="#0F172A", border="#94A3B8", h=28)
    draw_pill(draw, rx + 256, 116, "구분선 100% 연결 & 중앙 정렬", bg="#ECFDF5", fg="#047857", border="#10B981", font_size=10, pad_x=8, h_fixed=20)

    draw_rounded_rect(draw, (rx, 165, rx + 390, 320), radius=6, fill="#FFFFFF", outline="#CBD5E1", width=1)
    for i in range(5):
        ry_new = 171 + i * 29
        if i % 2 == 1:
            draw.rectangle((rx + 1, ry_new, rx + 389, ry_new + 29), fill="#F8FAFC")
        draw_checkbox(draw, rx + 10, ry_new, 29, f"00{i+1} · image{i+1}.bmp", checked=(i >= 2), enabled=True, box_s=13)
        draw.line([(rx + 1, ry_new + 29), (rx + 389, ry_new + 29)], fill="#E2E8F0", width=1)
    draw_pill(draw, rx + 20, 335, "끊김 없는 행 구분선 + 13×13px 비겹침 체크박스 + 수직 중앙 정렬", bg="#ECFDF5", fg="#047857", border="#10B981", font_size=10, pad_x=10, h_fixed=22)

    draw_vcentered_text(draw, 28, H - 38, 20, "※ 카드 02·03·04의 좌우 라벨 폭(92px / 72px)을 통일하여 모든 입력 박스의 수직 정렬선과 공간 효율성을 극대화했습니다.", f_reg(10), "#64748B")
    im.save(out_path)


if __name__ == "__main__":
    for out_dir in [
        Path("/tmp/review_uploaded/화면예시"),
        Path("/working_dir/c_da964b40fb7e87a7/artifacts/file_generation/ttl=63d/output"),
    ]:
        out_dir.mkdir(parents=True, exist_ok=True)
        render_main_window(out_dir / "1_문서추가_이미지목록.png", dark=False, completed=False)
        render_popup_window(out_dir / "2_미리보기_자르기설정.png")
        render_main_window(out_dir / "3_추출완료_결과요약.png", dark=True, completed=True)
        render_dropdown_comparison(out_dir / "4_드롭다운_가독성개선.png")
    print("Rendered all 4 updated screenshots successfully.")
