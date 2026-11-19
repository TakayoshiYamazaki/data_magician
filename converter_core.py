import csv
import datetime
import json
import os
import re
from typing import List, Dict, Any, Optional, Tuple

# 全角・半角変換テーブル
ZEN_CHARS = "０１２３４５６７８９ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ　"
HAN_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ "
ZEN_TO_HAN = str.maketrans(ZEN_CHARS, HAN_CHARS)
HAN_TO_ZEN = str.maketrans(HAN_CHARS, ZEN_CHARS)

TRANSFORM_OPTIONS = [
    ("none", "そのまま出力"),
    ("zenkaku", "全角変換（住所・病名等）"),
    ("hankaku", "半角変換（英数・記号）"),
    ("date_to_gengou", "和暦元号コード(1:令和/2:平成/3:昭和/4:大正/5:明治)"),
    ("date_to_wareki_year", "和暦年2桁(01-64)"),
    ("date_to_month", "月2桁(01-12)"),
    ("date_to_day", "日2桁(01-31)"),
    ("sex_code", "性別コード(男/1, 女/2)"),
]

PADDING_OPTIONS = [
    ("right_zero_or_space", "[S]右詰め・前ゼロ埋め(該当なし時はスペース埋め)"),
    ("right_zero", "右詰め・前ゼロ埋め(数値用)"),
    ("left_full_space", "左詰め・全角スペース埋め(漢字・住所用)"),
    ("left_space", "左詰め・半角スペース埋め(一般テキスト用)"),
    ("right_space", "右詰め・半角スペース埋め"),
]

MAPPING_TYPE_OPTIONS = [
    ("csv", "CSV列から取得"),
    ("const", "固定値（定数）"),
    ("blank", "空白（パディングのみ）"),
]

DEFAULT_CONFIG_PATH = "config.json"
DEFAULT_FORMATS_DIR = "formats"

DEFAULT_CONFIG = {
    "formats_directory": DEFAULT_FORMATS_DIR,
    "recent_formats_limit": 10,
    "last_used_format": os.path.join(DEFAULT_FORMATS_DIR, "hosp_in_odd.json"),
    "recent_formats": [
        os.path.join(DEFAULT_FORMATS_DIR, "hosp_in_odd.json"),
        os.path.join(DEFAULT_FORMATS_DIR, "hosp_in_even.json"),
        os.path.join(DEFAULT_FORMATS_DIR, "hosp_out_odd.json"),
        os.path.join(DEFAULT_FORMATS_DIR, "hosp_out_even.json"),
        os.path.join(DEFAULT_FORMATS_DIR, "hosp_discharge.json"),
        os.path.join(DEFAULT_FORMATS_DIR, "clinic_in.json"),
        os.path.join(DEFAULT_FORMATS_DIR, "clinic_out.json"),
        os.path.join(DEFAULT_FORMATS_DIR, "clinic_discharge.json"),
        os.path.join(DEFAULT_FORMATS_DIR, "dental.json"),
    ]
}

def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """設定ファイル（JSON形式）をロード。存在しないか破損時はデフォルトで補完・作成"""
    config = dict(DEFAULT_CONFIG)
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    if "formats_directory" in data:
                        config["formats_directory"] = str(data["formats_directory"])
                    if "recent_formats_limit" in data:
                        try:
                            config["recent_formats_limit"] = max(1, int(data["recent_formats_limit"]))
                        except (ValueError, TypeError):
                            pass
                    if "last_used_format" in data and isinstance(data["last_used_format"], str):
                        config["last_used_format"] = data["last_used_format"]
                    if "recent_formats" in data and isinstance(data["recent_formats"], list):
                        config["recent_formats"] = [str(p) for p in data["recent_formats"]]
        except Exception:
            pass
    else:
        # 設定ファイルが存在しない場合は作成
        save_config(config, config_path)
    return config

def save_config(config_data: Dict[str, Any], config_path: str = DEFAULT_CONFIG_PATH) -> None:
    """設定ファイル（JSON形式）を保存"""
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}")

def load_format_file(file_path: str) -> Dict[str, Any]:
    """1つのフォーマットファイル（JSON）をロード"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"フォーマットファイルが見つかりません: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"無効なフォーマットファイルです: {file_path}")

    # 形式正規化
    if "items" not in data:
        # リストそのもの、または旧設定保存形式への対応
        if isinstance(data, list):
            data = {"title": os.path.splitext(os.path.basename(file_path))[0], "items": data}
        else:
            raise ValueError(f"項目情報（items）が見つかりません: {file_path}")

    if not data.get("title"):
        data["title"] = os.path.splitext(os.path.basename(file_path))[0]

    if "total_len" not in data:
        data["total_len"] = sum(int(it.get("length", 1)) for it in data.get("items", []))

    return data

def save_format_file(file_path: str, title: str, items: List[Dict[str, Any]], extra_meta: Optional[Dict[str, Any]] = None) -> str:
    """1つのフォーマットをJSONファイルとして特定フォルダ等に保存"""
    dir_name = os.path.dirname(file_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    data = {
        "title": title.strip() or os.path.splitext(os.path.basename(file_path))[0],
        "total_len": sum(int(it.get("length", 1)) for it in items),
        "items": items
    }
    if extra_meta and isinstance(extra_meta, dict):
        for k, v in extra_meta.items():
            if k not in data:
                data[k] = v

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return file_path

def get_recent_formats(config: Dict[str, Any]) -> List[Tuple[str, str]]:
    """
    最近使用した順に設定ファイルで指定した件数（recent_formats_limit）分の
    フォーマット一覧 [(ファイルパス, 表示タイトル), ...] を取得。
    """
    limit = config.get("recent_formats_limit", 10)
    formats_dir = config.get("formats_directory", DEFAULT_FORMATS_DIR)

    recent_paths = list(config.get("recent_formats", []))
    result: List[Tuple[str, str]] = []
    seen_paths = set()

    # 1. recent_formats に登録されているファイルを順にチェック
    for path in recent_paths:
        if not path or path in seen_paths:
            continue
        if os.path.exists(path):
            try:
                data = load_format_file(path)
                title = data.get("title", os.path.splitext(os.path.basename(path))[0])
                result.append((path, title))
                seen_paths.add(path)
            except Exception:
                pass
        if len(result) >= limit:
            break

    # 2. まだ枠があり、特定フォルダ内に他のフォーマットファイルがあれば補完
    if len(result) < limit and os.path.isdir(formats_dir):
        try:
            for fname in sorted(os.listdir(formats_dir)):
                if fname.endswith(".json"):
                    fpath = os.path.join(formats_dir, fname)
                    if fpath not in seen_paths and os.path.exists(fpath):
                        try:
                            data = load_format_file(fpath)
                            title = data.get("title", os.path.splitext(fname)[0])
                            result.append((fpath, title))
                            seen_paths.add(fpath)
                        except Exception:
                            pass
                        if len(result) >= limit:
                            break
        except Exception:
            pass

    return result

def update_recent_format(format_path: str, config: Dict[str, Any], config_path: str = DEFAULT_CONFIG_PATH) -> None:
    """最近使用したフォーマットのリストを更新し、設定ファイルに記録"""
    config["last_used_format"] = format_path
    recent = config.get("recent_formats", [])
    
    # 既存にあれば削除して先頭へ
    new_recent = [p for p in recent if p != format_path]
    new_recent.insert(0, format_path)
    
    # 上限件数より少し多めに保持（後でlimitが拡張された場合にも備えるため2倍程度許容）
    limit = config.get("recent_formats_limit", 10)
    config["recent_formats"] = new_recent[:max(limit * 2, 50)]
    
    save_config(config, config_path)

def load_presets(preset_file: str = "presets_r8.json") -> Dict[str, Any]:
    """旧来の互換性用: formatsディレクトリまたはpresets_r8.jsonからプリセットを読み込む"""
    formats_dir = DEFAULT_FORMATS_DIR
    if os.path.isdir(formats_dir):
        result = {}
        for fname in os.listdir(formats_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(formats_dir, fname)
                try:
                    data = load_format_file(fpath)
                    key = os.path.splitext(fname)[0]
                    result[key] = data
                except Exception:
                    pass
        if result:
            return result
    """令和8年患者調査のプリセット定義をロード"""
    if os.path.exists(preset_file):
        try:
            with open(preset_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and any(isinstance(v, dict) for v in data.values()):
                    return data
        except Exception:
            pass

    # バックアップファイル等のフォールバック
    for fallback in [f"#{preset_file}#", "presets_r8.json.bak"]:
        if os.path.exists(fallback):
            try:
                with open(fallback, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and any(isinstance(v, dict) for v in data.values()):
                        return data
            except Exception:
                pass
    return {}

def convert_field_value(raw_val: Any, item: Dict[str, Any]) -> bytes:
    """単一フィールドの値を厚労省指定の固定長バイト列に変換"""
    mapping_type = item.get("mapping_type", "csv")
    length = int(item.get("length", 1))
    pad_type = item.get("pad", "left_space")
    transform = item.get("transform", "none")

    # 値の取得
    if mapping_type == "const":
        val_str = str(item.get("const_val", "")).strip()
    elif mapping_type == "blank":
        val_str = ""
    else:
        val_str = str(raw_val).strip() if raw_val is not None else ""

    # データ変換の適用
    if transform == "zenkaku":
        val_str = val_str.translate(HAN_TO_ZEN)
    elif transform == "hankaku":
        val_str = val_str.translate(ZEN_TO_HAN)
    elif transform in ["date_to_gengou", "date_to_wareki_year", "date_to_month", "date_to_day"]:
        clean_date = re.sub(r"[^\d]", "", val_str)
        if len(clean_date) >= 8:
            try:
                y = int(clean_date[:4])
                m = int(clean_date[4:6])
                d = int(clean_date[6:8])
                dt = datetime.date(y, m, d)
                if transform == "date_to_month":
                    val_str = f"{m:02d}"
                elif transform == "date_to_day":
                    val_str = f"{d:02d}"
                elif transform == "date_to_gengou":
                    if dt >= datetime.date(2019, 5, 1):
                        val_str = "1"  # 令和
                    elif dt >= datetime.date(1989, 1, 8):
                        val_str = "2"  # 平成
                    elif dt >= datetime.date(1926, 12, 25):
                        val_str = "3"  # 昭和
                    elif dt >= datetime.date(1912, 7, 30):
                        val_str = "4"  # 大正
                    else:
                        val_str = "5"  # 明治
                elif transform == "date_to_wareki_year":
                    if dt >= datetime.date(2019, 5, 1):
                        w_year = dt.year - 2018
                    elif dt >= datetime.date(1989, 1, 8):
                        w_year = dt.year - 1988
                    elif dt >= datetime.date(1926, 12, 25):
                        w_year = dt.year - 1925
                    elif dt >= datetime.date(1912, 7, 30):
                        w_year = dt.year - 1911
                    else:
                        w_year = dt.year - 1867
                    val_str = f"{w_year:02d}"
            except Exception:
                pass
    elif transform == "sex_code":
        s = val_str.strip()
        if s in ["1", "男", "男性", "M", "m", "Male"]:
            val_str = "1"
        elif s in ["2", "女", "女性", "F", "f", "Female"]:
            val_str = "2"

    # CP932 (Shift-JIS) バイト列へエンコード
    val_bytes = val_str.encode("cp932", errors="replace")

    # 指定桁数にスライス & 泣き別れ（全角文字の文字化け）防止
    if len(val_bytes) > length:
        val_bytes = val_bytes[:length]
        try:
            val_bytes.decode("cp932")
        except UnicodeDecodeError:
            # 奇数バイト等でマルチバイト文字が破損した場合、末尾を半角スペースに置き換え
            val_bytes = val_bytes[:-1] + b" "

    # 空値（該当なし）かどうかの判定（空文字、半角・全角空白、要領記号「△」など）
    clean_val = val_str.replace("　", " ").replace("△", "").strip()
    is_empty_or_na = (len(clean_val) == 0)

    # パディング処理
    pad_len = length - len(val_bytes)
    if pad_len > 0:
        if pad_type == "right_zero_or_space":
            if is_empty_or_na:
                # 該当なし（空値・△）の場合はすべて半角スペースで埋める！
                val_bytes = b" " * length
            else:
                # 値が存在する場合は右詰め前ゼロ埋め
                val_bytes = b"0" * pad_len + val_bytes
        elif pad_type == "right_zero":
            val_bytes = b"0" * pad_len + val_bytes
        elif pad_type == "right_space":
            val_bytes = b" " * pad_len + val_bytes
        elif pad_type == "left_full_space":
            # 全角スペース: b'\x81\x40' (2バイト)
            full_spaces = b"\x81\x40" * (pad_len // 2)
            if pad_len % 2 == 1:
                val_bytes = val_bytes + full_spaces + b" "
            else:
                val_bytes = val_bytes + full_spaces
        else:  # left_space
            val_bytes = val_bytes + b" " * pad_len
    elif pad_type == "right_zero_or_space" and is_empty_or_na:
        val_bytes = b" " * length

    return val_bytes

def convert_csv_row(row_dict: Dict[str, Any], items: List[Dict[str, Any]]) -> bytes:
    """1行のCSV辞書データを出力固定長バイト列に変換"""
    line_bytes = b""
    for item in items:
        csv_col = item.get("csv_col", "")
        raw_val = row_dict.get(csv_col, "") if csv_col else ""
        line_bytes += convert_field_value(raw_val, item)
    return line_bytes

def detect_csv_header(first_row: List[str]) -> bool:
    """CSVの先頭行がヘッダー（列名）かデータ行かを推測判定"""
    if not first_row:
        return True
    
    # 調査票のキーワード（日本語のヘッダー）が含まれているか
    known_headers = ["調査", "施設", "患者", "性別", "元号", "年", "月", "日", "都道府県", "主病", "病名", "外来", "入院", "受療"]
    text_matches = 0
    for cell in first_row[:15]:
        s = cell.strip()
        if any(k in s for k in known_headers):
            text_matches += 1
    if text_matches >= 2:
        return True

    # 調査票コード（1〜8）などの数値で始まり、数値項目が多い場合はデータ行（ヘッダーなし）
    numeric_count = 0
    for cell in first_row[:8]:
        s = cell.strip()
        if s.isdigit():
            numeric_count += 1
            
    if numeric_count >= 3:
        return False
    return True

def read_csv_samples(
    csv_path: str,
    encoding: str = "cp932",
    max_rows: int = 10,
    has_header: Optional[bool] = None
) -> Tuple[List[str], List[Dict[str, str]], int, bool, List[Tuple[str, str]]]:
    """
    CSVから一意の内部キー一覧、サンプル行辞書、総行数、ヘッダー有無フラグ、および(列キー, 表示用ラベル)一覧を返す
    """
    encodings_to_try = [encoding, "cp932", "shift_jis", "utf-8-sig", "utf-8"]
    raw_rows = []
    
    for enc in encodings_to_try:
        try:
            with open(csv_path, "r", encoding=enc, errors="replace") as f:
                reader = csv.reader(f)
                for r in reader:
                    if r:  # 空行を除外
                        raw_rows.append(r)
            if raw_rows:
                break
        except Exception:
            continue

    if not raw_rows:
        raise ValueError("CSVファイルの読み込みに失敗しました。ファイルが空か、文字コードを確認してください。")

    # ヘッダー有無の自動判定
    if has_header is None:
        has_header = detect_csv_header(raw_rows[0])

    col_count = max(len(r) for r in raw_rows[:20])
    
    col_keys = [f"col_{i+1}" for i in range(col_count)]
    col_choices = []  # (内部キー, 表示用ラベル)
    samples = []

    if has_header:
        headers_row = raw_rows[0]
        data_rows = raw_rows[1:]
        total_rows = len(data_rows)
        sample_preview_row = data_rows[0] if data_rows else []

        for i in range(col_count):
            key = f"col_{i+1}"
            h_name = headers_row[i].strip() if i < len(headers_row) else ""
            s_val = sample_preview_row[i].strip() if i < len(sample_preview_row) else ""
            
            if h_name and s_val:
                label = f"[{i+1}] {h_name} ({s_val[:10]})"
            elif h_name:
                label = f"[{i+1}] {h_name}"
            elif s_val:
                label = f"[{i+1}] 列{i+1} ({s_val[:10]})"
            else:
                label = f"[{i+1}] 列{i+1}"
                
            col_choices.append((key, label))

        for r in data_rows[:max_rows]:
            row_dict = {}
            for i in range(col_count):
                val = r[i] if i < len(r) else ""
                row_dict[f"col_{i+1}"] = val
            samples.append(row_dict)
    else:
        # ヘッダーなし: 1行目もデータとして扱う
        first_row_samples = raw_rows[0]
        data_rows = raw_rows
        total_rows = len(data_rows)

        for i in range(col_count):
            key = f"col_{i+1}"
            s_val = first_row_samples[i].strip() if i < len(first_row_samples) else ""
            if s_val:
                label = f"[{i+1}] 列{i+1} ({s_val[:12]})"
            else:
                label = f"[{i+1}] 列{i+1}"
            col_choices.append((key, label))

        for r in data_rows[:max_rows]:
            row_dict = {}
            for i in range(col_count):
                val = r[i] if i < len(r) else ""
                row_dict[f"col_{i+1}"] = val
            samples.append(row_dict)

    return col_keys, samples, total_rows, has_header, col_choices

def map_columns_sequentially(items: List[Dict[str, Any]], col_keys: List[str]) -> int:
    """出力項目の順序に従ってCSVの各列を順番に1対1で割り当てる"""
    matched = 0
    for i, item in enumerate(items):
        if i < len(col_keys):
            item["mapping_type"] = "csv"
            item["csv_col"] = col_keys[i]
            matched += 1
    return matched

def auto_map_columns(col_info: Any, items: List[Dict[str, Any]]) -> int:
    """
    CSV列の情報（タプルのリスト [(key, label), ...] または 文字列のリスト [col_name, ...]）
    を元に推測マッピングを行う。
    「主病」「主傷病名」「病名」などの表記揺れに完全対応。
    """
    matched_count = 0

    # 入力の正規化: タプルリスト [(key, label), ...] に変換
    col_choices: List[Tuple[str, str]] = []
    if isinstance(col_info, list):
        for entry in col_info:
            if isinstance(entry, (tuple, list)) and len(entry) >= 2:
                col_choices.append((str(entry[0]), str(entry[1])))
            elif isinstance(entry, (tuple, list)) and len(entry) == 1:
                col_choices.append((str(entry[0]), str(entry[0])))
            else:
                s = str(entry)
                col_choices.append((s, s))
    elif isinstance(col_info, dict):
        col_choices = [(str(k), str(v)) for k, v in col_info.items()]

    # キーワード辞書
    keywords_map = {
        "調査票種別": ["調査票種別", "調査種別", "票種別"],
        "施設番号": ["施設番号", "病院番号", "医療機関コード", "病院コード"],
        "患者番号": ["患者番号", "患者id", "カルテ番号", "patientid", "id", "患者no", "患者コード"],
        "性別": ["性別", "男女", "sex", "gender"],
        "出生年月日（元号）": ["元号", "生年月日元号", "誕生元号"],
        "出生年月日（年）": ["生年月日年", "誕生年", "生年"],
        "出生年月日（月）": ["生年月日月", "誕生月", "生月"],
        "出生年月日（日）": ["生年月日日", "誕生日", "生日"],
        "出生年月日": ["生年月日", "出生年月日", "誕生日", "birthday", "birthdate"],
        "患者の住所（当院と同・別）": ["都道府県居住地", "居住地", "当院と同・別", "同・別", "同別"],
        "患者の住所（都道府県）": ["住所都道府県", "都道府県", "県名", "prefecture"],
        "患者の住所（市郡）": ["住所市郡", "市郡", "市区町村", "郡"],
        "患者の住所（区町村）": ["住所区町村", "区町村", "町村"],
        "外来の種別（月）": ["前回診療月", "前回訪問月", "受診月"],
        "外来の種別（日）": ["前回診療日", "前回訪問日", "受診日"],
        "外来の種別": ["外来の種別", "外来種別", "来院種別"],
        "入院年月日（元号）": ["入院元号"],
        "入院年月日（年）": ["入院年"],
        "入院年月日（月）": ["入院月"],
        "入院年月日（日）": ["入院日"],
        "入院年月日": ["入院年月日", "入院日", "入棟日", "admissiondate"],
        "退院年月日": ["退院年月日", "退院日", "dischargedate"],
        "受療種別": ["受療の状況", "受療種別", "受療区分"],
        "主傷病名": [
            "主病", "主傷病名", "主傷病", "傷病名", "傷病", "病名", "主病名", 
            "診断名", "主要病名", "主要傷病名", "疾患名", "病態名", "disease"
        ],
        "肝疾患の状況": ["肝疾患の状況", "肝疾患", "肝炎"],
        "外傷の原因": ["外傷の原因", "外傷原因", "外傷", "事故原因"],
        "病床の種別": ["病床の種別", "病床種別", "病棟種別", "病床区分"],
        "紹介の状況": ["紹介の状況", "紹介状況", "紹介区分", "紹介"],
        "来院時の状況（通常・救急）": ["通常救急", "通常・救急", "来院状況", "救急"],
        "来院時の状況（診療時間）": ["診療時間", "受診時間"],
    }

    used_keys = set()

    for item in items:
        # 固定値がすでにある場合はスキップ
        if item.get("mapping_type") == "const" and item.get("const_val"):
            continue

        item_name = item.get("name", "")
        item_clean = re.sub(r"[\s\-_（）\(\)]", "", item_name).lower()

        matched_key = None

        # 1. 完全一致・包含一致
        for key, label in col_choices:
            if key in used_keys:
                continue
            # labelから [1] などを除去してヘッダー名を取り出す
            clean_lbl = re.sub(r"^\[\d+\]\s*", "", label)
            clean_lbl = re.sub(r"\s*\(.*?\)$", "", clean_lbl).strip()
            clean_lbl = re.sub(r"[\s\-_（）\(\)]", "", clean_lbl).lower()
            
            if clean_lbl and (item_clean == clean_lbl or item_clean in clean_lbl or clean_lbl in item_clean):
                matched_key = key
                break

        # 2. キーワード辞書一致
        if not matched_key:
            for dict_item_name, kw_list in keywords_map.items():
                if dict_item_name in item_name:
                    for key, label in col_choices:
                        if key in used_keys:
                            continue
                        clean_lbl = re.sub(r"^\[\d+\]\s*", "", label)
                        clean_lbl = re.sub(r"\s*\(.*?\)$", "", clean_lbl).strip()
                        clean_lbl = re.sub(r"[\s\-_（）\(\)]", "", clean_lbl).lower()
                        
                        if any(kw == clean_lbl or kw in clean_lbl for kw in kw_list):
                            matched_key = key
                            break
                    if matched_key:
                        break

        if matched_key:
            item["mapping_type"] = "csv"
            item["csv_col"] = matched_key
            used_keys.add(matched_key)

            # トランスフォームの推測
            if "元号" in item_name and any(d in item_name for d in ["出生", "入院", "退院"]):
                item["transform"] = "date_to_gengou"
            elif "（年）" in item_name and any(d in item_name for d in ["出生", "入院", "退院"]):
                item["transform"] = "date_to_wareki_year"
            elif "（月）" in item_name and any(d in item_name for d in ["出生", "入院", "退院"]):
                item["transform"] = "date_to_month"
            elif "（日）" in item_name and any(d in item_name for d in ["出生", "入院", "退院"]):
                item["transform"] = "date_to_day"
            elif "性別" in item_name:
                item["transform"] = "sex_code"
            matched_count += 1

    return matched_count

def generate_preview_lines(sample_rows: List[Dict[str, str]], items: List[Dict[str, Any]], max_rows: int = 5) -> List[Tuple[str, int]]:
    """サンプル行に対する固定長テキストプレビューを生成（文字列, バイト数）"""
    preview = []
    for row in sample_rows[:max_rows]:
        line_bytes = convert_csv_row(row, items)
        decoded = line_bytes.decode("cp932", errors="replace")
        preview.append((decoded, len(line_bytes)))
    return preview

def execute_batch_conversion(
    csv_path: str,
    output_path: str,
    items: List[Dict[str, Any]],
    csv_encoding: str = "cp932",
    output_newline: str = "\r\n",
    has_header: bool = True,
    progress_callback = None
) -> Dict[str, Any]:
    """固定長テキストへの一括変換処理"""
    count = 0
    total_bytes = 0
    line_length = sum(int(item.get("length", 1)) for item in items)

    encodings_to_try = [csv_encoding, "cp932", "shift_jis", "utf-8-sig", "utf-8"]
    f_in = None
    rows_reader = None

    for enc in encodings_to_try:
        try:
            f_in = open(csv_path, "r", encoding=enc, errors="replace")
            rows_reader = csv.reader(f_in)
            break
        except Exception:
            if f_in:
                f_in.close()
            continue

    if not rows_reader:
        raise ValueError(f"CSVファイルを開けませんでした: {csv_path}")

    newline_bytes = output_newline.encode("ascii")

    try:
        if has_header:
            next(rows_reader, None)  # ヘッダー行をスキップ

        with open(output_path, "wb") as f_out:
            for row in rows_reader:
                if not row:
                    continue
                # col_1, col_2 ... のインデックス辞書を作成
                row_dict = {f"col_{i+1}": (row[i] if i < len(row) else "") for i in range(len(row))}

                line_bytes = convert_csv_row(row_dict, items)
                f_out.write(line_bytes + newline_bytes)
                count += 1
                total_bytes += len(line_bytes) + len(newline_bytes)
                if progress_callback and count % 500 == 0:
                    progress_callback(count)
    finally:
        if f_in:
            f_in.close()

    return {
        "success": True,
        "rows_converted": count,
        "line_bytes": line_length,
        "total_file_bytes": total_bytes,
        "output_path": output_path
    }
