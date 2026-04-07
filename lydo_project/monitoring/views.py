import json
import datetime
import io
import math
import struct
import textwrap
import unicodedata
import zipfile
import zlib
from collections import Counter
from functools import lru_cache
from pathlib import Path
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.utils import timezone
from .age_rules import age_on_date, is_birthdate_aged_out as _shared_is_birthdate_aged_out, purge_aged_out_youths as _shared_purge_aged_out_youths
from .models import Youth, Barangay, UserBarangayAssignment, UserAccessLog

# Optional profanity filter (graceful fallback if package not installed)
try:
    from better_profanity import profanity
    profanity.load_censor_words()
    profanity.add_censor_words(['gago', 'puta', 'yawa', 'piste'])
    _PROFANITY_AVAILABLE = True
except ImportError:
    _PROFANITY_AVAILABLE = False

def _contains_profanity(text: str) -> bool:
    if not _PROFANITY_AVAILABLE:
        return False
    return profanity.contains_profanity(text)


def _is_system_admin(user) -> bool:
    return bool(getattr(user, 'is_authenticated', False) and (user.is_staff or user.is_superuser))


def _assigned_barangay(user):
    if not getattr(user, 'is_authenticated', False):
        return None
    assignment = getattr(user, 'barangay_assignment', None)
    return assignment.barangay if assignment else None


def _ordered_barangays_for_user(user):
    ordered = _ordered_barangays()
    if _is_system_admin(user):
        return ordered
    assigned = _assigned_barangay(user)
    if not assigned:
        return []
    return [barangay for barangay in ordered if barangay.id == assigned.id]


def _assert_barangay_access(request, barangay):
    if _is_system_admin(request.user):
        return None
    assigned = _assigned_barangay(request.user)
    if not assigned or assigned.id != barangay.id:
        return JsonResponse({'error': 'Forbidden for this barangay'}, status=403)
    return None


def _barangay_account_exists(barangay, exclude_user_id=None):
    assignments = UserBarangayAssignment.objects.filter(barangay=barangay)
    if exclude_user_id is not None:
        assignments = assignments.exclude(user_id=exclude_user_id)
    return assignments.exists()


def _log_user_access(request, user):
    UserAccessLog.objects.filter(user=user, logout_time__isnull=True).update(logout_time=timezone.now())
    if not request.session.session_key:
        request.session.save()
    assignment = getattr(user, 'barangay_assignment', None)
    UserAccessLog.objects.create(
        user=user,
        barangay=assignment.barangay if assignment else None,
        session_key=request.session.session_key or '',
    )


def _close_active_access_logs(user):
    UserAccessLog.objects.filter(user=user, logout_time__isnull=True).update(logout_time=timezone.now())


# Public page views
# PAGE VIEWS
# Page access control

@ensure_csrf_cookie
def index(request):
    """Dashboard page; redirect to login if not authenticated."""
    if not request.user.is_authenticated:
        return redirect('login_page')
    return render(request, 'dashboard.html')


def login_page(request):
    """Login page; redirect to dashboard if already authenticated."""
    if request.user.is_authenticated:
        return redirect('index')
    return render(request, 'login.html')


def register_page(request):
    """Public registration is disabled; account creation now happens in the admin area."""
    if request.user.is_authenticated:
        return redirect('index')
    return redirect('login_page')


def reports_page(request, bid=None):
    """Reports page."""
    if not request.user.is_authenticated:
        return redirect('login_page')
    return render(request, 'reports.html', {'barangay_id': bid})


def heatmap_page(request):
    """Barangay by age heatmap page."""
    if not request.user.is_authenticated:
        return redirect('login_page')
    return render(request, 'heatmap.html')


def account_page(request):
    """Admin-only barangay account activity page."""
    if not request.user.is_authenticated:
        return redirect('login_page')
    if not _is_system_admin(request.user):
        return redirect('index')
    return render(request, 'account.html')


def talent_sports_map_page(request):
    """Talent and sports preference heatmap page."""
    if not request.user.is_authenticated:
        return redirect('login_page')
    return render(request, 'talentsport.html')


SPORT_PREFERENCE_OPTIONS = [
    'Arnis',
    'Badminton',
    'Baseball',
    'Basketball',
    'Billiards',
    'BJJ',
    'Boxing',
    'Chess',
    'E-Sports',
    'Football',
    'Gymnastics',
    'Karate',
    'Martial Arts',
    'Pickleball',
    'Soccer',
    'Softball',
    'Swimming',
    'Taekwondo',
    'Tennis',
    'Track and Field',
    'Volleyball',
]

TALENT_PREFERENCE_OPTIONS = [
    'Acting / Drama',
    'Dance',
    'Drawing & Painting',
    'Musical Instruments (Piano, Guitar, Violin, etc.)',
    'Pottery & Sculpting',
    'Vocals / Choir',
]

OTHER_SPORTS_LABEL = 'Other Sports'
OTHER_TALENTS_LABEL = 'Other Talents'


def _choice_labels(field_name):
    """Return the human-readable choice labels defined on the Youth model."""
    return [label for _value, label in Youth._meta.get_field(field_name).choices]


def _safe_export_name(value):
    cleaned = ''.join(ch if ch.isalnum() or ch in (' ', '-', '_') else '_' for ch in value)
    cleaned = '_'.join(cleaned.split())
    return cleaned or 'barangay'


def _build_blank_form_context(barangay_name):
    return {
        'barangay_name': barangay_name,
        'municipality_name': 'Manolo Fortich',
        'province_name': 'Bukidnon',
        'generated_on': datetime.date.today().strftime('%B %d, %Y'),
        'civil_status_options': _choice_labels('civil_status'),
        'education_level_options': _choice_labels('education_level'),
        'tribe_options': _choice_labels('tribe_name'),
        'muslim_group_options': _choice_labels('muslim_group'),
        'osy_program_options': _choice_labels('osy_program_type'),
        'specific_needs_options': _choice_labels('specific_needs_condition'),
        'kk_no_reason_options': _choice_labels('kk_assembly_no_reason'),
        'sports_preference_options': sorted(SPORT_PREFERENCE_OPTIONS, key=str.casefold),
        'talent_preference_options': sorted(TALENT_PREFERENCE_OPTIONS, key=str.casefold),
    }


def _normalize_preference_option(value):
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    return ' '.join(normalized.casefold().split())


def _normalize_youth_name(value):
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = ''.join(ch if ch.isalnum() or ch.isspace() else ' ' for ch in normalized)
    return ' '.join(normalized.casefold().split())


def _find_duplicate_youth_record(name, birthdate, sex, exclude_id=None):
    normalized_name = _normalize_youth_name(name)
    if not normalized_name or not birthdate:
        return None

    queryset = Youth.objects.select_related('barangay').filter(birthdate=birthdate, sex=sex)
    if exclude_id:
        queryset = queryset.exclude(id=exclude_id)

    for youth in queryset:
        if _normalize_youth_name(youth.name) == normalized_name:
            return youth
    return None


def _duplicate_youth_response(request, duplicate_youth, requested_barangay):
    duplicate_purok = (duplicate_youth.purok or '').strip() or 'No purok recorded'
    current_barangay = duplicate_youth.barangay
    requested_name = requested_barangay.name if requested_barangay else 'the selected barangay'
    assigned = _assigned_barangay(request.user)

    if _is_system_admin(request.user):
        error = (
            f'Duplicate youth record detected. {duplicate_youth.name} is already registered in '
            f'{current_barangay.name}, {duplicate_youth.municipality} ({duplicate_purok}). '
            f'Open the existing record and update its barangay there instead of creating a new one.'
        )
    elif assigned and current_barangay.id == assigned.id:
        error = (
            f'Duplicate youth record detected. {duplicate_youth.name} is already registered in '
            f'{current_barangay.name}, {duplicate_youth.municipality} ({duplicate_purok}). '
            f'Use the existing record in {current_barangay.name} and change the address there if the youth moved to '
            f'{requested_name}.'
        )
    else:
        error = (
            f'Duplicate youth record detected. {duplicate_youth.name} is already registered in '
            f'{current_barangay.name}, {duplicate_youth.municipality} ({duplicate_purok}). '
            f'Only {current_barangay.name} can transfer this youth record to {requested_name}. '
            f'Please ask the current barangay to update the existing record instead of creating a new one.'
        )

    return JsonResponse(
        {
            'error': error,
            'duplicate_youth': True,
            'duplicate_barangay': current_barangay.name,
            'duplicate_municipality': duplicate_youth.municipality,
            'duplicate_purok': duplicate_youth.purok,
            'duplicate_record_id': duplicate_youth.id,
            'transfer_requires_origin_barangay': True,
            'current_barangay': current_barangay.name,
            'target_barangay': requested_name,
        },
        status=400,
    )


def _clean_preference_list(values, allowed_options):
    if not isinstance(values, list):
        return []
    normalized_lookup = {
        _normalize_preference_option(option): option
        for option in allowed_options
    }
    cleaned = []
    seen = set()
    for value in values:
        option = normalized_lookup.get(_normalize_preference_option(value))
        if not option or option in seen:
            continue
        seen.add(option)
        cleaned.append(option)
    return cleaned


def _serialize_preference_list(values, allowed_options):
    return json.dumps(_clean_preference_list(values, allowed_options))


def _parse_preference_list(raw_value, allowed_options):
    if isinstance(raw_value, list):
        data = raw_value
    else:
        try:
            data = json.loads(raw_value or '[]')
        except (TypeError, ValueError):
            data = []
    return _clean_preference_list(data, allowed_options)


def _format_custom_preference_entries(counter):
    return [
        {'label': label, 'count': count}
        for label, count in counter.most_common(5)
    ]


def _build_top_sport_overall_summary(youths):
    sport_totals = {
        label: {'male': 0, 'female': 0, 'total': 0}
        for label in [*SPORT_PREFERENCE_OPTIONS, OTHER_SPORTS_LABEL]
    }

    for youth in youths:
        sports = _parse_preference_list(youth.sports_preferences, SPORT_PREFERENCE_OPTIONS)
        sports_other = (youth.sports_preference_other or '').strip()
        sex = (youth.sex or '').strip().lower()
        sex_key = 'male' if sex == 'male' else 'female' if sex == 'female' else None

        for option in sports:
            if option not in sport_totals:
                continue
            sport_totals[option]['total'] += 1
            if sex_key:
                sport_totals[option][sex_key] += 1

        if sports_other:
            sport_totals[OTHER_SPORTS_LABEL]['total'] += 1
            if sex_key:
                sport_totals[OTHER_SPORTS_LABEL][sex_key] += 1

    ranked = [
        {'label': label, **counts}
        for label, counts in sport_totals.items()
        if counts['total'] > 0
    ]
    return max(ranked, key=lambda item: item['total'], default=None)


def _build_talent_sports_metric(youths, option_labels, category_key):
    age_columns = [str(age) for age in range(15, 31)]
    counts = {
        label: {age: 0 for age in age_columns}
        for label in option_labels
    }
    sex_totals = {
        label: {'male': 0, 'female': 0}
        for label in option_labels
    }
    custom_counter = Counter()

    for youth in youths:
        birthdate = youth.birthdate
        if not birthdate:
            continue
        age = age_on_date(birthdate)
        age_key = str(age) if age is not None else ''
        if age_key not in age_columns:
            continue
        sex = (youth.sex or '').strip().lower()
        sex_key = 'male' if sex == 'male' else 'female' if sex == 'female' else None

        sports = _parse_preference_list(youth.sports_preferences, SPORT_PREFERENCE_OPTIONS)
        talents = _parse_preference_list(youth.talent_preferences, TALENT_PREFERENCE_OPTIONS)
        sports_other = (youth.sports_preference_other or '').strip()
        talents_other = (youth.talent_preference_other or '').strip()

        if category_key in ('all', 'sports'):
            for option in sports:
                if option in counts:
                    counts[option][age_key] += 1
                    if sex_key:
                        sex_totals[option][sex_key] += 1
            if sports_other and OTHER_SPORTS_LABEL in counts:
                counts[OTHER_SPORTS_LABEL][age_key] += 1
                if sex_key:
                    sex_totals[OTHER_SPORTS_LABEL][sex_key] += 1
                custom_counter[sports_other] += 1

        if category_key in ('all', 'talents'):
            for option in talents:
                if option in counts:
                    counts[option][age_key] += 1
                    if sex_key:
                        sex_totals[option][sex_key] += 1
            if talents_other and OTHER_TALENTS_LABEL in counts:
                counts[OTHER_TALENTS_LABEL][age_key] += 1
                if sex_key:
                    sex_totals[OTHER_TALENTS_LABEL][sex_key] += 1
                custom_counter[talents_other] += 1

    rows = []
    max_cell_value = 0
    age_totals = {age: 0 for age in age_columns}

    for label in option_labels:
        age_counts = counts[label]
        total = sum(age_counts.values())
        max_cell_value = max(max_cell_value, max(age_counts.values()) if age_counts else 0)
        for age, value in age_counts.items():
            age_totals[age] += value
        rows.append({
            'label': label,
            'ages': age_counts,
            'total': total,
            'male': sex_totals[label]['male'],
            'female': sex_totals[label]['female'],
        })

    populated_rows = [row for row in rows if row['total'] > 0]
    strongest = max(populated_rows, key=lambda row: row['total'], default=None)
    weakest = min(populated_rows, key=lambda row: row['total'], default=None)
    peak_age = max(age_totals.items(), key=lambda item: item[1], default=('15', 0))

    return {
        'rows': rows,
        'age_columns': age_columns,
        'max_cell_value': max_cell_value,
        'top_preference': strongest,
        'least_preference': weakest,
        'peak_age': {'age': peak_age[0], 'count': peak_age[1]},
        'custom_entries': _format_custom_preference_entries(custom_counter),
    }


def _talent_sports_scope_label(user):
    if _is_system_admin(user):
        return 'All Barangays'
    assigned = _assigned_barangay(user)
    return assigned.name if assigned else 'Assigned Barangay'


def _pdf_safe_text(value):
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = value.encode('ascii', 'ignore').decode('ascii')
    value = value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    return value.replace('\r', '').replace('\n', ' ')


def _wrap_pdf_text(text, max_width, font_size):
    text = unicodedata.normalize('NFKD', str(text or ''))
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = text.replace('\r', '').replace('\n', ' ')
    if not text:
        return []
    approx_chars = max(12, int(max_width / max(font_size * 0.52, 1)))
    return textwrap.wrap(text, width=approx_chars, break_long_words=False, break_on_hyphens=False) or [text]


_REPO_ROOT = Path(__file__).resolve().parents[2]
_LYDO_LOGO_PATH = _REPO_ROOT / 'frontend' / 'images' / 'logo.png'
_PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def _png_paeth(a, b, c):
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


@lru_cache(maxsize=4)
def _load_png_for_pdf(path_value):
    data = Path(path_value).read_bytes()
    if not data.startswith(_PNG_SIGNATURE):
        raise ValueError('Unsupported image format; expected PNG.')

    width = height = None
    bit_depth = color_type = compression = filter_method = interlace = None
    idat_chunks = bytearray()
    cursor = len(_PNG_SIGNATURE)

    while cursor + 8 <= len(data):
        chunk_length = struct.unpack('>I', data[cursor:cursor + 4])[0]
        cursor += 4
        chunk_type = data[cursor:cursor + 4]
        cursor += 4
        chunk_data = data[cursor:cursor + chunk_length]
        cursor += chunk_length + 4  # chunk bytes + CRC

        if chunk_type == b'IHDR':
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                '>IIBBBBB',
                chunk_data,
            )
        elif chunk_type == b'IDAT':
            idat_chunks.extend(chunk_data)
        elif chunk_type == b'IEND':
            break

    if not width or not height:
        raise ValueError('PNG image is missing IHDR metadata.')
    if bit_depth != 8:
        raise ValueError('Only 8-bit PNG images are supported.')
    if compression != 0 or filter_method != 0 or interlace != 0:
        raise ValueError('Only non-interlaced PNG images are supported.')

    channel_map = {0: 1, 2: 3, 6: 4}
    if color_type not in channel_map:
        raise ValueError(f'Unsupported PNG color type: {color_type}')

    channels = channel_map[color_type]
    bytes_per_pixel = channels
    stride = width * channels
    decoded = zlib.decompress(bytes(idat_chunks))
    expected_min_size = height * (stride + 1)
    if len(decoded) < expected_min_size:
        raise ValueError('PNG image data is incomplete.')

    raw_pixels = bytearray(height * stride)
    previous_row = bytearray(stride)
    src = 0
    dest = 0

    for _ in range(height):
        filter_type = decoded[src]
        src += 1
        row = bytearray(decoded[src:src + stride])
        src += stride

        if filter_type == 1:
            for index in range(bytes_per_pixel, stride):
                row[index] = (row[index] + row[index - bytes_per_pixel]) & 0xFF
        elif filter_type == 2:
            for index in range(stride):
                row[index] = (row[index] + previous_row[index]) & 0xFF
        elif filter_type == 3:
            for index in range(stride):
                left = row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
                up = previous_row[index]
                row[index] = (row[index] + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            for index in range(stride):
                left = row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
                up = previous_row[index]
                up_left = previous_row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
                row[index] = (row[index] + _png_paeth(left, up, up_left)) & 0xFF
        elif filter_type != 0:
            raise ValueError(f'Unsupported PNG filter type: {filter_type}')

        raw_pixels[dest:dest + stride] = row
        previous_row = row
        dest += stride

    if color_type == 6:
        # Flatten transparency onto white so the logo renders reliably in PDF viewers.
        rgb_bytes = bytearray(width * height * 3)
        rgb_index = 0
        for pixel_index in range(0, len(raw_pixels), 4):
            alpha = raw_pixels[pixel_index + 3]
            if alpha == 255:
                red = raw_pixels[pixel_index]
                green = raw_pixels[pixel_index + 1]
                blue = raw_pixels[pixel_index + 2]
            elif alpha == 0:
                red = green = blue = 255
            else:
                red = ((raw_pixels[pixel_index] * alpha) + (255 * (255 - alpha))) // 255
                green = ((raw_pixels[pixel_index + 1] * alpha) + (255 * (255 - alpha))) // 255
                blue = ((raw_pixels[pixel_index + 2] * alpha) + (255 * (255 - alpha))) // 255
            rgb_bytes[rgb_index] = red
            rgb_bytes[rgb_index + 1] = green
            rgb_bytes[rgb_index + 2] = blue
            rgb_index += 3
        return {
            'width': width,
            'height': height,
            'color_space': 'DeviceRGB',
            'data': zlib.compress(bytes(rgb_bytes)),
            'alpha': None,
        }

    color_space = 'DeviceGray' if color_type == 0 else 'DeviceRGB'
    return {
        'width': width,
        'height': height,
        'color_space': color_space,
        'data': zlib.compress(bytes(raw_pixels)),
        'alpha': None,
    }


class _SimplePdf:
    """Small PDF writer using built-in Helvetica fonts only."""

    def __init__(self, page_width=595.28, page_height=841.89):
        self.page_width = float(page_width)
        self.page_height = float(page_height)
        self.pages = []
        self._page_xobjects = []
        self._images = {}
        self._commands = None
        self._current_xobjects = None

    def add_page(self):
        if self._commands is not None:
            self.pages.append('\n'.join(self._commands))
            self._page_xobjects.append(set(self._current_xobjects or set()))
        self._commands = []
        self._current_xobjects = set()

    def _append(self, command):
        if self._commands is None:
            self.add_page()
        self._commands.append(command)

    def text(self, x, y, text, size=11, bold=False, color=(0, 0, 0)):
        font = 'F2' if bold else 'F1'
        r, g, b = color
        self._append(f"{r:.3f} {g:.3f} {b:.3f} rg")
        self._append(
            f"BT /{font} {size:.2f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({_pdf_safe_text(text)}) Tj ET"
        )

    def line(self, x1, y1, x2, y2, width=1, color=(0, 0, 0)):
        r, g, b = color
        self._append(f"{r:.3f} {g:.3f} {b:.3f} RG")
        self._append(f"{width:.2f} w")
        self._append(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def rect(self, x, y, width, height, stroke=(0, 0, 0), fill=None, line_width=1):
        sr, sg, sb = stroke
        self._append(f"{sr:.3f} {sg:.3f} {sb:.3f} RG")
        self._append(f"{line_width:.2f} w")
        if fill is not None:
            fr, fg, fb = fill
            self._append(f"{fr:.3f} {fg:.3f} {fb:.3f} rg")
            self._append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re B")
        else:
            self._append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re S")

    def draw_png(self, name, png_path, x, top, width, height):
        if name not in self._images:
            self._images[name] = _load_png_for_pdf(str(png_path))
        if self._commands is None:
            self.add_page()
        self._current_xobjects.add(name)
        y = self.page_height - top - height
        self._append('q')
        self._append(f"{width:.2f} 0 0 {height:.2f} {x:.2f} {y:.2f} cm")
        self._append(f"/{name} Do")
        self._append('Q')

    def build(self):
        if self._commands is not None:
            self.pages.append('\n'.join(self._commands))
            self._page_xobjects.append(set(self._current_xobjects or set()))
            self._commands = None
            self._current_xobjects = None

        font_regular_id = 3
        font_bold_id = 4
        next_object_id = 5
        image_ids = {}
        mask_ids = {}
        for image_name, image in self._images.items():
            if image.get('alpha') is not None:
                mask_ids[image_name] = next_object_id
                next_object_id += 1
            image_ids[image_name] = next_object_id
            next_object_id += 1

        page_ids = []
        content_ids = []
        for page_index in range(len(self.pages)):
            content_ids.append(next_object_id)
            next_object_id += 1
            page_ids.append(next_object_id)
            next_object_id += 1

        object_count = next_object_id - 1

        objects = [None] * (object_count + 1)
        objects[1] = "<< /Type /Catalog /Pages 2 0 R >>"
        kids = ' '.join(f"{page_id} 0 R" for page_id in page_ids)
        objects[2] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>"
        objects[3] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
        objects[4] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"

        for image_name, image in self._images.items():
            alpha_bytes = image.get('alpha')
            if alpha_bytes is not None:
                mask_id = mask_ids[image_name]
                mask_header = (
                    f"<< /Type /XObject /Subtype /Image /Width {image['width']} /Height {image['height']} "
                    f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode "
                    f"/Length {len(alpha_bytes)} >>\nstream\n"
                ).encode('latin-1')
                objects[mask_id] = mask_header + alpha_bytes + b"\nendstream"

            image_bytes = image['data']
            smask_ref = f" /SMask {mask_ids[image_name]} 0 R" if image_name in mask_ids else ""
            image_header = (
                f"<< /Type /XObject /Subtype /Image /Width {image['width']} /Height {image['height']} "
                f"/ColorSpace /{image['color_space']} /BitsPerComponent 8 /Filter /FlateDecode"
                f"{smask_ref} /Length {len(image_bytes)} >>\nstream\n"
            ).encode('latin-1')
            objects[image_ids[image_name]] = image_header + image_bytes + b"\nendstream"

        for page_index, content in enumerate(self.pages):
            content_bytes = content.encode('latin-1', 'replace')
            content_id = content_ids[page_index]
            page_id = page_ids[page_index]
            objects[content_id] = f"<< /Length {len(content_bytes)} >>\nstream\n{content}\nendstream"
            xobjects = self._page_xobjects[page_index] if page_index < len(self._page_xobjects) else set()
            xobject_resource = ""
            if xobjects:
                xobject_refs = ' '.join(f"/{name} {image_ids[name]} 0 R" for name in sorted(xobjects))
                xobject_resource = f" /XObject << {xobject_refs} >>"
            objects[page_id] = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.page_width:.2f} {self.page_height:.2f}] "
                f"/Resources << /Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >>{xobject_resource} >> "
                f"/Contents {content_id} 0 R >>"
            )

        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0] * (object_count + 1)
        for obj_id in range(1, object_count + 1):
            offsets[obj_id] = len(output)
            output.extend(f"{obj_id} 0 obj\n".encode("latin-1"))
            obj_value = objects[obj_id]
            if isinstance(obj_value, bytes):
                output.extend(obj_value)
            else:
                output.extend(obj_value.encode("latin-1"))
            output.extend(b"\nendobj\n")

        xref_offset = len(output)
        output.extend(f"xref\n0 {object_count + 1}\n".encode("latin-1"))
        output.extend(b"0000000000 65535 f \n")
        for obj_id in range(1, object_count + 1):
            output.extend(f"{offsets[obj_id]:010d} 00000 n \n".encode("latin-1"))
        output.extend(
            (
                f"trailer\n<< /Size {object_count + 1} /Root 1 0 R >>\n"
                f"startxref\n{xref_offset}\n%%EOF"
            ).encode("latin-1")
        )
        return bytes(output)


def _draw_wrapped_text(pdf, x, top, text, max_width, size=10, bold=False, color=(0, 0, 0), leading=None):
    leading = leading or (size + 3)
    lines = _wrap_pdf_text(text, max_width, size)
    for index, line in enumerate(lines):
        pdf.text(x, pdf.page_height - top - (index * leading) - size, line, size=size, bold=bold, color=color)
    return top + (len(lines) * leading)


def _draw_line_field(pdf, x, top, width, label, line_y_offset=28):
    pdf.text(x, pdf.page_height - top - 9, label, size=8.5, bold=True, color=(0.26, 0.34, 0.47))
    baseline_y = pdf.page_height - top - line_y_offset
    pdf.line(x, baseline_y, x + width, baseline_y, width=0.8, color=(0.35, 0.42, 0.55))
    return top + line_y_offset + 12


def _draw_checkbox_item(pdf, x, top, label, max_width, size=9.5):
    box_size = 9
    rect_y = pdf.page_height - top - box_size - 1
    pdf.rect(x, rect_y, box_size, box_size, stroke=(0.32, 0.40, 0.52), line_width=0.8)
    text_top = top - 1
    used_top = _draw_wrapped_text(pdf, x + box_size + 6, text_top, label, max_width - box_size - 6, size=size)
    return max(box_size + 8, used_top - top + 2)


def _draw_checkbox_list(pdf, x, top, width, title, options, columns=1, size=9.5, row_gap=6, col_gap=16):
    top = _draw_wrapped_text(pdf, x, top, title, width, size=9.5, bold=True, color=(0.10, 0.22, 0.44))
    top += 6
    columns = max(1, columns)
    col_width = (width - ((columns - 1) * col_gap)) / columns
    rows = int(math.ceil(len(options) / columns)) if options else 0
    for row in range(rows):
        heights = []
        for col in range(columns):
            idx = (row * columns) + col
            if idx >= len(options):
                continue
            item_x = x + (col * (col_width + col_gap))
            item_height = _draw_checkbox_item(pdf, item_x, top, options[idx], col_width, size=size)
            heights.append(item_height)
        top += (max(heights) if heights else 0) + row_gap
    return top


def _draw_page_header(pdf, barangay_name, page_number, total_pages, include_logo=False):
    left = 36
    right = pdf.page_width - 36
    top = 28
    title_x = left
    if include_logo and _LYDO_LOGO_PATH.exists():
        try:
            pdf.draw_png('LydoLogo', _LYDO_LOGO_PATH, left, 10, 38, 38)
            title_x += 48
        except (OSError, ValueError):
            title_x = left
    pdf.text(title_x, pdf.page_height - top - 18, "LYDO Youth Profile Form", size=18, bold=True, color=(0.10, 0.22, 0.44))
    pdf.text(
        right - 145,
        pdf.page_height - top - 10,
        f"Barangay: {barangay_name}",
        size=9,
        bold=True,
        color=(0.28, 0.35, 0.46),
    )
    pdf.line(left, pdf.page_height - 56, right, pdf.page_height - 56, width=1.1, color=(0.10, 0.22, 0.44))
    pdf.text(left, 20, "Copyright (c) 2026 LYDO Office. All rights reserved.", size=7.5, color=(0.45, 0.52, 0.62))
    pdf.text(right - 56, 20, f"Page {page_number} of {total_pages}", size=8.5, color=(0.45, 0.52, 0.62))


def _draw_section_banner(pdf, top, title):
    x = 36
    width = pdf.page_width - 72
    height = 20
    pdf.rect(x, pdf.page_height - top - height, width, height, stroke=(0.10, 0.22, 0.44), fill=(0.10, 0.22, 0.44), line_width=0.8)
    pdf.text(x + 8, pdf.page_height - top - 14, title, size=10.5, bold=True, color=(1, 1, 1))
    return top + height + 12


def _build_blank_form_pdf(barangay_name, include_logo=False):
    context = _build_blank_form_context(barangay_name)
    pdf = _SimplePdf()
    total_pages = 2
    content_width = pdf.page_width - 72
    half_gap = 18
    half_width = (content_width - half_gap) / 2
    left_x = 36
    right_x = left_x + half_width + half_gap

    # Page 1: Personal information + education and work
    pdf.add_page()
    _draw_page_header(pdf, context['barangay_name'], 1, total_pages, include_logo=include_logo)
    top = 66
    top = _draw_section_banner(pdf, top, "PERSONAL INFORMATION")
    row_top = top
    family_width = 182
    given_width = 182
    middle_width = content_width - family_width - given_width - 24
    _draw_line_field(pdf, left_x, row_top, family_width, "Family Name", line_y_offset=24)
    _draw_line_field(pdf, left_x + family_width + 12, row_top, given_width, "Given Name", line_y_offset=24)
    top = _draw_line_field(
        pdf,
        left_x + family_width + given_width + 24,
        row_top,
        middle_width,
        "Middle Initial",
        line_y_offset=24,
    )
    row_top = top
    _draw_line_field(pdf, left_x, row_top, 150, "Birthdate", line_y_offset=24)
    _draw_line_field(pdf, left_x + 170, row_top, 70, "Age", line_y_offset=24)
    sex_bottom = _draw_checkbox_list(
        pdf,
        left_x + 265,
        row_top,
        128,
        "Sex",
        ["Male", "Female"],
        columns=2,
        size=8.8,
        row_gap=3,
        col_gap=6,
    )
    mobile_bottom = _draw_line_field(
        pdf,
        left_x + family_width + given_width + 24,
        row_top,
        middle_width,
        "Mobile Number",
        line_y_offset=24,
    )
    top = max(sex_bottom, mobile_bottom, row_top + 36) + 2
    top = _draw_checkbox_list(
        pdf,
        left_x,
        top,
        content_width,
        "Civil Status",
        context['civil_status_options'],
        columns=5,
        size=8.4,
        row_gap=3,
        col_gap=8,
    )
    row_top = top
    _draw_line_field(pdf, left_x, row_top, half_width, "Religion", line_y_offset=24)
    top = _draw_line_field(pdf, right_x, row_top, half_width, "Purok", line_y_offset=24)
    row_top = top
    _draw_line_field(pdf, left_x, row_top, half_width, "Barangay", line_y_offset=24)
    pdf.text(left_x + 2, pdf.page_height - row_top - 23, context['barangay_name'], size=9.5, bold=True, color=(0.14, 0.19, 0.27))
    _draw_line_field(pdf, right_x, row_top, half_width, "Municipality", line_y_offset=24)
    pdf.text(right_x + 2, pdf.page_height - row_top - 23, context['municipality_name'], size=9.5, bold=True, color=(0.14, 0.19, 0.27))
    top = row_top + 30
    row_top = top
    _draw_line_field(pdf, left_x, row_top, half_width, "Province", line_y_offset=24)
    pdf.text(left_x + 2, pdf.page_height - row_top - 23, context['province_name'], size=9.5, bold=True, color=(0.14, 0.19, 0.27))
    _draw_line_field(pdf, right_x, row_top, half_width, "Email Address", line_y_offset=24)
    top = row_top + 30

    top += 10
    top = _draw_section_banner(pdf, top, "EDUCATION AND WORK")
    top = _draw_checkbox_list(
        pdf,
        left_x,
        top,
        content_width,
        "Highest Education",
        context['education_level_options'],
        columns=4,
        size=8.2,
        row_gap=4,
    )
    row_top = top + 2
    _draw_line_field(pdf, left_x, row_top, half_width, "Course / Degree", line_y_offset=24)
    top = _draw_line_field(pdf, right_x, row_top, half_width, "School / University", line_y_offset=24)
    row_top = top
    _draw_line_field(pdf, left_x, row_top, half_width, "Work Status", line_y_offset=24)
    scholarship_bottom = _draw_checkbox_list(
        pdf,
        right_x,
        row_top,
        half_width,
        "Scholarship",
        ["Scholarship Beneficiary"],
        columns=1,
        size=8.6,
        row_gap=4,
    )
    top = max(row_top + 36, scholarship_bottom)
    top = _draw_line_field(pdf, right_x, top + 2, half_width, "Scholarship Program", line_y_offset=24)

    top += 10
    top = _draw_section_banner(pdf, top, "CIVIC AND OTHER")
    row_top = top
    left_bottom = _draw_checkbox_list(
        pdf,
        left_x,
        row_top,
        half_width,
        "Voter Status",
        [
            "SK Voter",
            "National Voter",
            "Voted in Last SK Election",
        ],
        columns=1,
        size=8.6,
        row_gap=4,
    )
    right_bottom = _draw_checkbox_list(
        pdf,
        right_x,
        row_top,
        half_width,
        "4Ps and Family",
        ["4Ps Beneficiary"],
        columns=1,
        size=8.6,
        row_gap=4,
    )
    right_bottom = _draw_line_field(pdf, right_x, right_bottom + 4, half_width, "Number of Children", line_y_offset=24)
    top = max(left_bottom, right_bottom) + 8
    row_top = top
    left_bottom = _draw_checkbox_list(
        pdf,
        left_x,
        row_top,
        half_width,
        "KK Assembly Attendance",
        ["Attended KK Assembly", "Did not attend"],
        columns=1,
        size=8.6,
        row_gap=4,
    )
    left_bottom = _draw_line_field(pdf, left_x, left_bottom + 4, half_width, "If yes, how many times", line_y_offset=24)
    right_bottom = _draw_checkbox_list(
        pdf,
        right_x,
        row_top,
        half_width,
        "If no, reason",
        context['kk_no_reason_options'],
        columns=1,
        size=8.6,
        row_gap=4,
    )
    _draw_line_field(pdf, right_x, right_bottom + 4, half_width, "Other reason / notes", line_y_offset=24)

    # Page 2: Groups and needs + signatures
    pdf.add_page()
    _draw_page_header(pdf, context['barangay_name'], 2, total_pages, include_logo=include_logo)
    top = 66
    top = _draw_section_banner(pdf, top, "GROUPS AND NEEDS")
    top = _draw_checkbox_list(
        pdf,
        left_x,
        top,
        content_width,
        "Youth Classification",
        [
            "In School Youth",
            "Out of School Youth",
            "Working Youth",
            "Unemployed Youth",
            "Indigenous People Youth",
            "Youth with Disability",
        ],
        columns=3,
        size=8.4,
        row_gap=3,
        col_gap=10,
    )
    top += 4
    row_top = top
    left_bottom = _draw_checkbox_list(
        pdf,
        left_x,
        row_top,
        half_width,
        "Out of School Youth Details",
        [
            "Willing to enroll",
            "Not willing to enroll",
            *context['osy_program_options'],
        ],
        columns=2,
        size=8.0,
        row_gap=3,
        col_gap=8,
    )
    left_bottom = _draw_line_field(
        pdf,
        left_x,
        left_bottom + 2,
        half_width,
        "Reason if not enrolling",
        line_y_offset=24,
    )
    top = left_bottom + 6
    top = _draw_checkbox_list(
        pdf,
        left_x,
        top,
        content_width,
        "Specific Needs",
        ["Mark if not applicable", *context['specific_needs_options']],
        columns=4,
        size=7.2,
        row_gap=2,
        col_gap=10,
    )
    top = _draw_line_field(
        pdf,
        left_x,
        top + 2,
        content_width,
        "Others (if not above, specify youth needs)",
        line_y_offset=24,
    )
    cultural_top = top + 8
    left_bottom = _draw_checkbox_list(
        pdf,
        left_x,
        cultural_top,
        half_width,
        "7 Tribes / Indigenous Group",
        ["Mark if not part of the 7 tribes", *context['tribe_options']],
        columns=3,
        size=7.6,
        row_gap=2,
        col_gap=6,
    )
    left_bottom = _draw_line_field(pdf, left_x, left_bottom + 2, half_width, "Selected Tribe", line_y_offset=24)
    right_bottom = _draw_checkbox_list(
        pdf,
        right_x,
        cultural_top,
        half_width,
        "Muslim Group",
        ["Mark if not a Muslim", *context['muslim_group_options']],
        columns=3,
        size=7.5,
        row_gap=2,
        col_gap=6,
    )
    right_bottom = _draw_line_field(pdf, right_x, right_bottom + 2, half_width, "Selected Group", line_y_offset=24)
    preference_top = max(left_bottom, right_bottom) + 16
    preference_bottom_left = _draw_checkbox_list(
        pdf,
        left_x,
        preference_top,
        half_width,
        "Talent / Sports Preference - Sports",
        context['sports_preference_options'],
        columns=3,
        size=6.9,
        row_gap=2,
        col_gap=8,
    )
    preference_bottom_left = _draw_line_field(
        pdf,
        left_x,
        preference_bottom_left + 2,
        half_width,
        "Other Sports Preference",
        line_y_offset=24,
    )
    preference_bottom_right = _draw_checkbox_list(
        pdf,
        right_x,
        preference_top,
        half_width,
        "Talent / Sports Preference - Talents",
        context['talent_preference_options'],
        columns=2,
        size=6.9,
        row_gap=2,
        col_gap=8,
    )
    preference_bottom_right = _draw_line_field(
        pdf,
        right_x,
        preference_bottom_right + 2,
        half_width,
        "Other Talent Preference",
        line_y_offset=24,
    )
    signature_top = max(preference_bottom_left, preference_bottom_right) + 24 + 56
    signature_top = min(signature_top, pdf.page_height - 88)
    signature_top = max(signature_top, max(preference_bottom_left, preference_bottom_right) + 24)
    pdf.line(left_x, pdf.page_height - signature_top, left_x + half_width - 10, pdf.page_height - signature_top, width=0.8, color=(0.35, 0.42, 0.55))
    pdf.line(right_x, pdf.page_height - signature_top, right_x + half_width - 10, pdf.page_height - signature_top, width=0.8, color=(0.35, 0.42, 0.55))
    pdf.text(left_x + 50, pdf.page_height - signature_top - 16, "Signature of Youth Respondent", size=9, color=(0.33, 0.40, 0.50))
    pdf.text(right_x + 30, pdf.page_height - signature_top - 16, "Signature of Encoder/ LYDO Officer", size=9, color=(0.33, 0.40, 0.50))

    return pdf.build()


@login_required(login_url='/login/')
def download_barangay_blank_form(request, bid):
    """Download one blank youth intake form PDF for the selected barangay."""
    _seed_barangays()
    barangay = get_object_or_404(Barangay, id=bid)
    access_error = _assert_barangay_access(request, barangay)
    if access_error:
        return access_error
    pdf_bytes = _build_blank_form_pdf(barangay.name, include_logo=True)
    filename = f"Youth_Profile_Form_{_safe_export_name(barangay.name)}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required(login_url='/login/')
def download_blank_form_pack(request):
    """Download a ZIP pack with one printable blank youth form PDF per barangay."""
    if not _is_system_admin(request.user):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    _seed_barangays()
    barangays = list(Barangay.objects.all().order_by('name'))

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for index, barangay in enumerate(barangays, start=1):
            safe_name = _safe_export_name(barangay.name)
            folder_name = f"{index:02d}_{safe_name}"
            file_name = f"Youth_Profile_Form_{safe_name}.pdf"
            zip_path = f"{folder_name}/{file_name}"
            zip_file.writestr(zip_path, _build_blank_form_pdf(barangay.name, include_logo=True))

    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="barangay_youth_profile_forms.zip"'
    return response


# Authentication views
# AUTH API ENDPOINTS
# Registration and login handlers

@csrf_exempt
@login_required(login_url='/login/')
def register_view(request):
    if not _is_system_admin(request.user):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    username = data.get('username', '').strip()
    password = data.get('password', '')
    barangay_id = data.get('barangay_id')

    if not username or not password or not barangay_id:
        return JsonResponse({'error': 'Username, password, and assigned barangay are required'}, status=400)

    if User.objects.filter(username=username).exists():
        return JsonResponse({'error': 'Username already exists'}, status=400)

    try:
        validate_password(password)
    except ValidationError as exc:
        return JsonResponse({'error': ' '.join(exc.messages)}, status=400)

    _seed_barangays()
    try:
        barangay = Barangay.objects.get(id=barangay_id)
    except Barangay.DoesNotExist:
        return JsonResponse({'error': 'Selected barangay does not exist'}, status=400)
    if _barangay_account_exists(barangay):
        return JsonResponse({'error': f'{barangay.name} already has an assigned account'}, status=400)
    user = User.objects.create_user(username=username, password=password, email='')
    UserBarangayAssignment.objects.create(user=user, barangay=barangay)
    return JsonResponse({
        'message': 'Account created successfully',
        'user_id': user.id,
        'username': user.username,
        'barangay_name': barangay.name,
    })


@csrf_exempt
def login_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return JsonResponse({'error': 'Username and password are required'}, status=400)

    existing_user = User.objects.filter(username=username).first()
    if existing_user and not existing_user.is_active:
        return JsonResponse({'error': 'This account has been disabled by the administrator'}, status=403)

    user = authenticate(request, username=username, password=password)
    if user is not None:
        login(request, user)
        _log_user_access(request, user)
        assignment = getattr(user, 'barangay_assignment', None)
        return JsonResponse({
            'message': 'Login successful',
            'username': user.username,
            'is_admin': _is_system_admin(user),
            'barangay_name': assignment.barangay.name if assignment else None,
        })

    return JsonResponse({'error': 'Invalid credentials'}, status=401)


def logout_view(request):
    if request.user.is_authenticated:
        _close_active_access_logs(request.user)
    logout(request)
    return JsonResponse({'message': 'Logged out successfully'})


def user_info_view(request):
    """Return current authentication state."""
    if request.user.is_authenticated:
        assignment = getattr(request.user, 'barangay_assignment', None)
        return JsonResponse({
            'is_authenticated': True,
            'username': request.user.username,
            'is_admin': _is_system_admin(request.user),
            'barangay_id': assignment.barangay_id if assignment else None,
            'barangay_name': assignment.barangay.name if assignment else None,
        })
    return JsonResponse({'is_authenticated': False}, status=401)


@login_required(login_url='/login/')
def admin_account_activity_api(request):
    if not _is_system_admin(request.user):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    assignments = UserBarangayAssignment.objects.select_related('user', 'barangay').order_by('barangay__name', 'user__username')
    rows = []
    for assignment in assignments:
        latest_log = assignment.user.access_logs.order_by('-login_time').first()
        last_logout = assignment.user.access_logs.exclude(logout_time__isnull=True).order_by('-logout_time').first()
        rows.append({
            'user_id': assignment.user.id,
            'username': assignment.user.username,
            'barangay_id': assignment.barangay.id,
            'barangay_name': assignment.barangay.name,
            'is_account_active': assignment.user.is_active,
            'is_logged_in': bool(latest_log and latest_log.logout_time is None),
            'login_time': latest_log.login_time.isoformat() if latest_log else None,
            'logout_time': last_logout.logout_time.isoformat() if last_logout and last_logout.logout_time else None,
        })

    active_barangays = sorted({row['barangay_name'] for row in rows if row['is_logged_in']})
    return JsonResponse({
        'rows': rows,
        'active_barangays': active_barangays,
        'active_count': sum(1 for row in rows if row['is_logged_in']),
    })


@csrf_exempt
@login_required(login_url='/login/')
def admin_disable_account_api(request):
    if not _is_system_admin(request.user):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_id = data.get('user_id')
    if not user_id:
        return JsonResponse({'error': 'User ID is required'}, status=400)

    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)

    if _is_system_admin(target_user):
        return JsonResponse({'error': 'Admin accounts cannot be disabled here'}, status=400)

    target_user.is_active = False
    target_user.save(update_fields=['is_active'])
    _close_active_access_logs(target_user)
    return JsonResponse({'message': 'Account disabled successfully'})


@csrf_exempt
@login_required(login_url='/login/')
def admin_enable_account_api(request):
    if not _is_system_admin(request.user):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_id = data.get('user_id')
    if not user_id:
        return JsonResponse({'error': 'User ID is required'}, status=400)

    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)

    if _is_system_admin(target_user):
        return JsonResponse({'error': 'Admin accounts cannot be enabled here'}, status=400)

    target_user.is_active = True
    target_user.save(update_fields=['is_active'])
    return JsonResponse({'message': 'Account enabled successfully'})


@csrf_exempt
@login_required(login_url='/login/')
def admin_update_account_api(request):
    if not _is_system_admin(request.user):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_id = data.get('user_id')
    username = data.get('username', '').strip()
    barangay_id = data.get('barangay_id')
    password = data.get('password', '')

    if not user_id:
        return JsonResponse({'error': 'User ID is required'}, status=400)
    if not username or not barangay_id:
        return JsonResponse({'error': 'Username and assigned barangay are required'}, status=400)

    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)

    if _is_system_admin(target_user):
        return JsonResponse({'error': 'Admin accounts cannot be edited here'}, status=400)

    if User.objects.exclude(id=target_user.id).filter(username=username).exists():
        return JsonResponse({'error': 'Username already exists'}, status=400)

    _seed_barangays()
    try:
        barangay = Barangay.objects.get(id=barangay_id)
    except Barangay.DoesNotExist:
        return JsonResponse({'error': 'Selected barangay does not exist'}, status=400)
    if _barangay_account_exists(barangay, exclude_user_id=target_user.id):
        return JsonResponse({'error': f'{barangay.name} already has an assigned account'}, status=400)

    target_user.username = username
    update_fields = ['username']

    if password:
        try:
            validate_password(password, user=target_user)
        except ValidationError as exc:
            return JsonResponse({'error': ' '.join(exc.messages)}, status=400)
        target_user.set_password(password)
        update_fields.append('password')

    target_user.save(update_fields=update_fields)
    UserBarangayAssignment.objects.update_or_create(
        user=target_user,
        defaults={'barangay': barangay},
    )

    return JsonResponse({
        'message': 'Account updated successfully',
        'user_id': target_user.id,
        'username': target_user.username,
        'barangay_name': barangay.name,
    })


# Barangay seed data and summary endpoints
# BARANGAY API ENDPOINTS
# Default barangay list used for initialization

_DEFAULT_BARANGAYS = [
    "Agusan Canyon", "Alae", "Dahilayan", "Dalirig", "Damilag", "Diclum",
    "Guilang-guilang", "Kalugmanan", "Lindaban", "Lingion", "Lunocan", "Maluko",
    "Mambatangan", "Mampayag", "Mantibugao", "Minsuro", "San Miguel", "Sankanan",
    "Santiago", "Santo Niño", "Tankulan", "Ticala",
]


def _normalize_barangay_name(name):
    value = unicodedata.normalize('NFKD', str(name or ''))
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    value = ' '.join(value.lower().split())
    aliases = {
        'dicklum': 'diclum',
    }
    return aliases.get(value, value)


_NEARBY_BARANGAY_GROUPS = [
    ("Alae", "Mantibugao", "Mambatangan"),
    ("Damilag", "Agusan Canyon", "San Miguel"),
    ("Tankulan", "Diclum", "Dicklum", "Santo Niño", "Lunocan"),
    ("Maluko", "Dalirig"),
    ("Dahilayan", "Mampayag", "Guilang-guilang", "Kalugmanan"),
    ("Lingion", "Sankanan", "Santiago", "Lindaban", "Ticala", "Minsuro"),
]


def _is_birthdate_aged_out(birthdate):
    return _shared_is_birthdate_aged_out(birthdate)


def _purge_aged_out_youths():
    return _shared_purge_aged_out_youths()


def _build_nearby_barangay_lookup():
    lookup = {}
    for group in _NEARBY_BARANGAY_GROUPS:
        normalized_group = {_normalize_barangay_name(name) for name in group if name}
        for name in normalized_group:
            lookup.setdefault(name, set()).update(normalized_group - {name})
    return lookup


_NEARBY_BARANGAY_LOOKUP = _build_nearby_barangay_lookup()


def _allowed_barangay_transfer_names(current_barangay):
    current_name = _normalize_barangay_name(current_barangay.name if current_barangay else '')
    allowed_names = _NEARBY_BARANGAY_LOOKUP.get(current_name, set())
    barangays_by_name = {
        _normalize_barangay_name(barangay.name): barangay.name
        for barangay in Barangay.objects.all()
    }
    return sorted(barangays_by_name[name] for name in allowed_names if name in barangays_by_name)


def _is_allowed_barangay_transfer(current_barangay, new_barangay):
    if not current_barangay or not new_barangay:
        return False
    if current_barangay.id == new_barangay.id:
        return True
    current_name = _normalize_barangay_name(current_barangay.name)
    new_name = _normalize_barangay_name(new_barangay.name)
    return new_name in _NEARBY_BARANGAY_LOOKUP.get(current_name, set())


def _seed_barangays():
    """Seed the 22 default barangays if the table is empty."""
    if not Barangay.objects.exists():
        Barangay.objects.bulk_create(
            [Barangay(name=n) for n in _DEFAULT_BARANGAYS],
            ignore_conflicts=True,
        )


def _ordered_barangays():
    """Return barangays in the official legend order."""
    _seed_barangays()
    by_name = {_normalize_barangay_name(barangay.name): barangay for barangay in Barangay.objects.all()}
    default_names = [_normalize_barangay_name(name) for name in _DEFAULT_BARANGAYS]
    ordered = [by_name[name] for name in default_names if name in by_name]
    remaining = sorted(
        [
            barangay for normalized_name, barangay in by_name.items()
            if normalized_name not in default_names
        ],
        key=lambda barangay: barangay.name,
    )
    return ordered + remaining


def barangays_api(request):
    """Return all barangays as a JSON array: [{id, name}, ...]"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized. Please login.'}, status=401)
    data = [{'id': barangay.id, 'name': barangay.name} for barangay in _ordered_barangays_for_user(request.user)]
    return JsonResponse(data, safe=False)


def all_barangays_api(request):
    """Return the full 22-barangay list for authenticated transfer/edit flows."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized. Please login.'}, status=401)
    data = [{'id': barangay.id, 'name': barangay.name} for barangay in _ordered_barangays()]
    return JsonResponse(data, safe=False)


def barangay_summary(request, bid):
    """Return aggregated demographic summary for a single barangay."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized. Please login.'}, status=401)
    _purge_aged_out_youths()
    barangay = get_object_or_404(Barangay, id=bid)
    access_error = _assert_barangay_access(request, barangay)
    if access_error:
        return access_error
    youths   = Youth.objects.filter(barangay=barangay)

    age_counts   = {}
    sex_by_age   = {}
    civil_by_age = {}
    edu_by_age   = {}

    for y in youths:
        age = str(y.age)
        age_counts[age] = age_counts.get(age, 0) + 1

        for bucket, key in [
            (sex_by_age,   y.sex             or 'Unknown'),
            (civil_by_age, y.civil_status    or 'Unknown'),
            (edu_by_age,   y.education_level or 'Unknown'),
        ]:
            bucket.setdefault(key, {})
            bucket[key][age] = bucket[key].get(age, 0) + 1

    sex_counts = {
        r['sex'] or 'Unknown': r['count']
        for r in youths.values('sex').annotate(count=Count('id'))
    }
    civil_counts = {
        r['civil_status'] or 'Unknown': r['count']
        for r in youths.values('civil_status').annotate(count=Count('id'))
    }
    edu_counts = {
        r['education_level'] or 'Unknown': r['count']
        for r in youths.values('education_level').annotate(count=Count('id'))
    }

    return JsonResponse({
        'barangay_id':       barangay.id,
        'barangay_name':     barangay.name,
        'total':             youths.count(),
        'sex':               sex_counts,
        'sex_by_age':        sex_by_age,
        'ages':              age_counts,
        'civil_status':      civil_counts,
        'civil_by_age':      civil_by_age,
        'education':         edu_counts,
        'education_by_age':  edu_by_age,
        'pwd':               youths.filter(is_pwd=True).count(),
        'pwd_male':          youths.filter(is_pwd=True, sex='Male').count(),
        'pwd_female':        youths.filter(is_pwd=True, sex='Female').count(),
        'fourps':            youths.filter(is_4ps=True).count(),
        'fourps_male':       youths.filter(is_4ps=True, sex='Male').count(),
        'fourps_female':     youths.filter(is_4ps=True, sex='Female').count(),
        'working':           youths.filter(is_working_youth=True).count(),
        'working_male':      youths.filter(is_working_youth=True, sex='Male').count(),
        'working_female':    youths.filter(is_working_youth=True, sex='Female').count(),
        'unemployed':        youths.filter(is_unemployed=True).count(),
        'unemployed_male':   youths.filter(is_unemployed=True, sex='Male').count(),
        'unemployed_female': youths.filter(is_unemployed=True, sex='Female').count(),
        'ip':                youths.filter(is_ip=True).count(),
        'ip_male':           youths.filter(is_ip=True, sex='Male').count(),
        'ip_female':         youths.filter(is_ip=True, sex='Female').count(),
        'muslim':            youths.filter(is_muslim=True).count(),
        'muslim_male':       youths.filter(is_muslim=True, sex='Male').count(),
        'muslim_female':     youths.filter(is_muslim=True, sex='Female').count(),
        'osy':               youths.filter(is_osy=True).count(),
        'osy_male':          youths.filter(is_osy=True, sex='Male').count(),
        'osy_female':        youths.filter(is_osy=True, sex='Female').count(),
    })


def demographics_api(request):
    """Per-barangay demographic breakdown used by the interactive reports table."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized. Please login.'}, status=401)
    _purge_aged_out_youths()
    _seed_barangays()

    metric_keys = ('isy', 'osy', 'yd', 'iy', 'ip', 'mu', 'wk', 'uy')
    barangays = list(_ordered_barangays_for_user(request.user))
    demo_data = {
        b.name: {
            'total': 0,
            'male': 0,
            'female': 0,
            **{key: 0 for key in metric_keys},
            **{f'{key}_male': 0 for key in metric_keys},
            **{f'{key}_female': 0 for key in metric_keys},
        }
        for b in barangays
    }

    allowed_ids = [barangay.id for barangay in barangays]
    for y in (Youth.objects
              .select_related('barangay')
              .filter(barangay_id__in=allowed_ids)
              .values(
                  'barangay__name', 'sex', 'is_in_school', 'is_osy',
                  'is_working_youth', 'is_unemployed', 'is_pwd', 'is_4ps', 'is_ip', 'is_muslim'
              )):
        name = y['barangay__name']
        if name not in demo_data:
            continue

        d = demo_data[name]
        sex = (y['sex'] or '').strip().lower()

        d['total'] += 1
        if sex == 'male':
            d['male'] += 1
        elif sex == 'female':
            d['female'] += 1

        matches = []
        if y['is_in_school']:
            matches.append('isy')
        if y['is_osy']:
            matches.append('osy')
        if y['is_working_youth']:
            matches.append('wk')
        if y['is_unemployed']:
            matches.append('uy')
        if y['is_pwd']:
            matches.append('iy')
        if y['is_ip']:
            matches.append('ip')
        if y['is_muslim']:
            matches.append('mu')
        if y['is_4ps']:
            matches.append('yd')

        for key in matches:
            d[key] += 1
            if sex == 'male':
                d[f'{key}_male'] += 1
            elif sex == 'female':
                d[f'{key}_female'] += 1

    return JsonResponse(demo_data)


def _build_barangay_age_heatmap_rows(youths, barangays, age_columns):
    today = datetime.date.today()

    matrix = {
        b.name: {age: 0 for age in age_columns}
        for b in barangays
    }

    max_count = 0

    for y in youths:
        birthdate = y['birthdate']
        if not birthdate:
            continue

        age = today.year - birthdate.year - (
            (today.month, today.day) < (birthdate.month, birthdate.day)
        )
        age_key = str(age)
        barangay_name = y['barangay__name']

        if barangay_name not in matrix or age_key not in matrix[barangay_name]:
            continue

        matrix[barangay_name][age_key] += 1
        if matrix[barangay_name][age_key] > max_count:
            max_count = matrix[barangay_name][age_key]

    rows = []
    for b in barangays:
        counts = matrix[b.name]
        total = sum(counts.values())
        peak_age = max(age_columns, key=lambda age: counts[age]) if total else None
        rows.append({
            'barangay': b.name,
            'counts': counts,
            'total': total,
            'peak_age': peak_age,
            'peak_count': counts[peak_age] if peak_age else 0,
        })

    return rows, max_count


def heatmap_api(request):
    """Barangay by age heatmap data for key youth categories."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized. Please login.'}, status=401)
    _purge_aged_out_youths()
    age_columns = [str(age) for age in range(15, 31)]
    barangays = _ordered_barangays_for_user(request.user)
    allowed_ids = [barangay.id for barangay in barangays]

    metric_queries = {
        'unemployed': Youth.objects.filter(is_unemployed=True, birthdate__isnull=False, barangay_id__in=allowed_ids),
        'osy': Youth.objects.filter(is_osy=True, birthdate__isnull=False, barangay_id__in=allowed_ids),
        'pwd': Youth.objects.filter(is_pwd=True, birthdate__isnull=False, barangay_id__in=allowed_ids),
    }

    metrics = {}
    for metric_key, queryset in metric_queries.items():
        youths = queryset.values('barangay__name', 'birthdate')
        rows, max_count = _build_barangay_age_heatmap_rows(youths, barangays, age_columns)
        metrics[metric_key] = {
            'rows': rows,
            'max_count': max_count,
        }

    return JsonResponse({
        'ages': age_columns,
        'default_metric': 'unemployed',
        'metric_order': ['unemployed', 'osy', 'pwd'],
        'metrics': metrics,
    })


def talent_sports_map_api(request):
    """Preference heatmap data for youth talents and sports by age."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized. Please login.'}, status=401)
    _purge_aged_out_youths()

    youths = Youth.objects.select_related('barangay').filter(birthdate__isnull=False)
    if not _is_system_admin(request.user):
        assigned = _assigned_barangay(request.user)
        if not assigned:
            return JsonResponse({
                'scope_label': _talent_sports_scope_label(request.user),
                'default_metric': 'all',
                'metric_order': ['all', 'sports', 'talents'],
                'metrics': {},
            })
        youths = youths.filter(barangay=assigned)

    youth_list = list(youths)
    metrics = {
        'all': _build_talent_sports_metric(
            youth_list,
            [*SPORT_PREFERENCE_OPTIONS, OTHER_SPORTS_LABEL, *TALENT_PREFERENCE_OPTIONS, OTHER_TALENTS_LABEL],
            'all',
        ),
        'sports': _build_talent_sports_metric(
            youth_list,
            [*SPORT_PREFERENCE_OPTIONS, OTHER_SPORTS_LABEL],
            'sports',
        ),
        'talents': _build_talent_sports_metric(
            youth_list,
            [*TALENT_PREFERENCE_OPTIONS, OTHER_TALENTS_LABEL],
            'talents',
        ),
    }

    return JsonResponse({
        'scope_label': _talent_sports_scope_label(request.user),
        'default_metric': 'all',
        'metric_order': ['all', 'sports', 'talents'],
        'metrics': metrics,
        'top_sport_overall': _build_top_sport_overall_summary(youth_list),
    })


def unemployed_heatmap_api(request):
    """Backward-compatible alias for the heatmap API."""
    return heatmap_api(request)


# Youth analytics APIs
# YOUTH CRUD API
# Youth profile API endpoints

@csrf_exempt
def youth_api(request):
    """
    GET: public list of all youth profiles
    POST: create a new profile (auth required)
    PUT: update an existing profile (auth required)
    DELETE: remove a profile (auth required)
    """

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized. Please login.'}, status=401)
    _purge_aged_out_youths()

    # GET: list youth profiles
    if request.method == 'GET':
        youths = Youth.objects.select_related('barangay').all()
        if not _is_system_admin(request.user):
            assigned = _assigned_barangay(request.user)
            if not assigned:
                return JsonResponse([], safe=False)
            youths = youths.filter(barangay=assigned)
        data = []
        for y in youths:
            data.append({
                'id':              y.id,
                'name':            y.name,
                'age':             y.age,
                'sex':             y.sex,
                'barangay_name':   y.barangay.name,
                'barangay_id':     y.barangay.id,
                'education_level': y.education_level,
                'full_data': {
                    'birthdate':                str(y.birthdate) if y.birthdate else '',
                    'civil_status':             y.civil_status,
                    'religion':                 y.religion,
                    'purok':                    y.purok,
                    'barangay_id':              y.barangay.id,
                    'barangay_name':            y.barangay.name,
                    'municipality':             y.municipality,
                    'province':                 y.province,
                    'email':                    y.email,
                    'contact_number':           y.contact_number,
                    'is_in_school':             y.is_in_school,
                    'is_osy':                   y.is_osy,
                    'osy_willing_to_enroll':    y.osy_willing_to_enroll,
                    'osy_program_type':         y.osy_program_type,
                    'osy_reason_no_enroll':     y.osy_reason_no_enroll,
                    'is_working_youth':         y.is_working_youth,
                    'is_unemployed':           y.is_unemployed,
                    'is_unemployed_youth':     y.is_unemployed,
                    'is_pwd':                   y.is_pwd,
                    'disability_type':          y.disability_type,
                    'has_specific_needs':       y.has_specific_needs,
                    'specific_needs_condition': y.specific_needs_condition,
                    'is_ip':                    y.is_ip,
                    'tribe_name':               y.tribe_name,
                    'is_muslim':                y.is_muslim,
                    'muslim_group':             y.muslim_group,
                    'course':                   y.course,
                    'school_name':              y.school_name,
                    'is_scholar':               y.is_scholar,
                    'scholarship_program':      y.scholarship_program,
                    'work_status':              y.work_status,
                    'sports_preferences':       _parse_preference_list(y.sports_preferences, SPORT_PREFERENCE_OPTIONS),
                    'talent_preferences':       _parse_preference_list(y.talent_preferences, TALENT_PREFERENCE_OPTIONS),
                    'sports_preference_other':  y.sports_preference_other,
                    'talent_preference_other':  y.talent_preference_other,
                    'registered_voter_sk':      y.registered_voter_sk,
                    'registered_voter_national':y.registered_voter_national,
                    'is_non_voter':             y.is_non_voter,
                    'voted_last_sk':            y.voted_last_sk,
                    'attended_kk_assembly':     y.attended_kk_assembly,
                    'kk_assembly_times':        y.kk_assembly_times,
                    'kk_assembly_no_reason':    y.kk_assembly_no_reason,
                    'is_4ps':                   y.is_4ps,
                    'number_of_children':       y.number_of_children,
                },
            })
        return JsonResponse(data, safe=False)

    # POST / PUT
    if request.method in ('POST', 'PUT'):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        try:
            name = data.get('name', '').strip()
            if not name:
                return JsonResponse({'error': 'Name is required'}, status=400)
            if _contains_profanity(name):
                return JsonResponse(
                    {'error': 'Inappropriate language detected in name.'}, status=400)

            barangay = get_object_or_404(Barangay, id=data.get('barangay_id'))
            if request.method == 'POST':
                access_error = _assert_barangay_access(request, barangay)
                if access_error:
                    return access_error

            def get_bool(key):
                return bool(data.get(key, False))

            def get_bool_alias(*keys):
                for key in keys:
                    if key in data:
                        return bool(data.get(key, False))
                return False

            def get_int(key, default=0):
                try:
                    return int(data.get(key) or default)
                except (ValueError, TypeError):
                    return default

            birthdate_value = data.get('birthdate') or None
            parsed_birthdate = None
            if birthdate_value:
                try:
                    parsed_birthdate = datetime.date.fromisoformat(birthdate_value)
                except ValueError:
                    return JsonResponse({'error': 'Birthdate must use YYYY-MM-DD format'}, status=400)
                if _is_birthdate_aged_out(parsed_birthdate):
                    detected_age = age_on_date(parsed_birthdate)
                    return JsonResponse(
                        {
                            'error': f'This person is already {detected_age} years old. The system only allows records for ages 30 and below.',
                            'age_blocked': True,
                            'age': detected_age,
                        },
                        status=400,
                    )

            sex_value = data.get('sex')

            is_non_voter = get_bool('is_non_voter')
            registered_voter_sk = get_bool('registered_voter_sk')
            registered_voter_national = get_bool('registered_voter_national')
            voted_last_sk = get_bool('voted_last_sk')
            sports_preferences = _serialize_preference_list(
                data.get('sports_preferences', []),
                SPORT_PREFERENCE_OPTIONS,
            )
            talent_preferences = _serialize_preference_list(
                data.get('talent_preferences', []),
                TALENT_PREFERENCE_OPTIONS,
            )
            sports_preference_other = str(data.get('sports_preference_other') or '').strip()
            talent_preference_other = str(data.get('talent_preference_other') or '').strip()

            if is_non_voter:
                registered_voter_sk = False
                registered_voter_national = False
                voted_last_sk = False
            elif registered_voter_sk or registered_voter_national or voted_last_sk:
                is_non_voter = False

            fields = {
                'name':             name,
                'birthdate':        birthdate_value,
                'sex':              data.get('sex'),
                'civil_status':     data.get('civil_status'),
                'religion':         data.get('religion'),
                'purok':            data.get('purok'),
                'barangay':         barangay,
                'email':            data.get('email'),
                'contact_number':   data.get('contact_number'),
                'is_in_school':     get_bool('is_in_school'),
                'is_osy':           get_bool('is_osy'),
                'osy_willing_to_enroll': get_bool('osy_willing_to_enroll'),
                'osy_program_type': data.get('osy_program_type'),
                'osy_reason_no_enroll': data.get('osy_reason_no_enroll'),
                'is_working_youth': get_bool('is_working_youth'),
                'is_unemployed':   get_bool_alias('is_unemployed_youth', 'is_unemployed'),
                'is_pwd':           get_bool('is_pwd'),
                'disability_type':  data.get('disability_type'),
                'has_specific_needs': get_bool('has_specific_needs'),
                'specific_needs_condition': data.get('specific_needs_condition'),
                'is_ip':            get_bool('is_ip'),
                'tribe_name':       data.get('tribe_name'),
                'is_muslim':        get_bool('is_muslim'),
                'muslim_group':     data.get('muslim_group'),
                'education_level':  data.get('education_level'),
                'course':           data.get('course'),
                'school_name':      data.get('school_name'),
                'is_scholar':       get_bool('is_scholar'),
                'scholarship_program': data.get('scholarship_program'),
                'work_status':      data.get('work_status'),
                'sports_preferences': sports_preferences,
                'talent_preferences': talent_preferences,
                'sports_preference_other': sports_preference_other,
                'talent_preference_other': talent_preference_other,
                'registered_voter_sk':      registered_voter_sk,
                'registered_voter_national': registered_voter_national,
                'is_non_voter':     is_non_voter,
                'voted_last_sk':    voted_last_sk,
                'attended_kk_assembly': get_bool('attended_kk_assembly'),
                'kk_assembly_times': get_int('kk_assembly_times'),
                'kk_assembly_no_reason': data.get('kk_assembly_no_reason'),
                'is_4ps':           get_bool('is_4ps'),
                'number_of_children': get_int('number_of_children'),
            }

            if request.method == 'POST':
                duplicate_youth = _find_duplicate_youth_record(name, parsed_birthdate, sex_value)
                if duplicate_youth:
                    return _duplicate_youth_response(request, duplicate_youth, barangay)
                Youth.objects.create(**fields)
                return JsonResponse({'message': 'Youth profile added successfully'})

            # PUT updates an existing record
            youth_id = data.get('id')
            if not youth_id:
                return JsonResponse({'error': 'ID is required for update'}, status=400)
            youth = get_object_or_404(Youth, id=youth_id)
            existing_access_error = _assert_barangay_access(request, youth.barangay)
            if existing_access_error:
                return existing_access_error
            duplicate_youth = _find_duplicate_youth_record(name, parsed_birthdate, sex_value, exclude_id=youth.id)
            if duplicate_youth:
                return _duplicate_youth_response(request, duplicate_youth, barangay)
            is_barangay_changed = youth.barangay_id != barangay.id
            if is_barangay_changed and not _is_system_admin(request.user):
                if not bool(data.get('confirm_barangay_transfer')):
                    return JsonResponse(
                        {
                            'error': f"{youth.name} is currently registered in {youth.barangay.name}. Confirm the move to {barangay.name} to continue.",
                            'requires_confirmation': True,
                            'current_barangay': youth.barangay.name,
                            'target_barangay': barangay.name,
                        },
                        status=400,
                    )
            for key, value in fields.items():
                setattr(youth, key, value)
            youth.save()
            return JsonResponse({'message': 'Youth profile updated successfully'})

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    # DELETE
    if request.method == 'DELETE':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        try:
            youth = get_object_or_404(Youth, id=data.get('id'))
            access_error = _assert_barangay_access(request, youth.barangay)
            if access_error:
                return access_error
            youth.delete()
            return JsonResponse({'message': 'Youth profile deleted successfully'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Method not allowed'}, status=405)
