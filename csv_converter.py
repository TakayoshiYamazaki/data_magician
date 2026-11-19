import flet as ft
import os
import json
import csv
import traceback
from typing import List, Dict, Any, Optional, Tuple

import converter_core

def main(page: ft.Page):
    # --- ページ基本設定 ---
    page.title = "DataMagician - CSV→固定長テキスト変換ツール"
    page.window.width = 1320
    page.window.height = 880
    page.window.min_width = 1000
    page.window.min_height = 700
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 15

    # --- 設定ファイルとアプリケーション状態のロード ---
    config = converter_core.load_config()
    state = {
        "config": config,
        "current_format_path": "",
        "current_format_title": "",
        "req_total_len": 0,
        "csv_path": "",
        "csv_headers": [],
        "csv_col_choices": [],  # (key, label)
        "csv_samples": [],
        "csv_total_rows": 0,
        "csv_encoding": "cp932",
        "has_header": True,     # 先頭行がヘッダーかどうか
        "items": [],            # 現在編集中のマッピング定義リスト
        "output_path": ""
    }

    # 前回使用したフォーマットの自動読み込み・プリセット（データ初期化）
    init_path = state["config"].get("last_used_format", "")
    if not init_path or not os.path.exists(init_path):
        formats_dir = state["config"].get("formats_directory", "formats")
        init_path = os.path.join(formats_dir, "hosp_in_odd.json")
        if not os.path.exists(init_path) and os.path.isdir(formats_dir):
            jsons = [f for f in os.listdir(formats_dir) if f.endswith(".json")]
            if jsons:
                init_path = os.path.join(formats_dir, sorted(jsons)[0])

    if os.path.exists(init_path):
        try:
            data = converter_core.load_format_file(init_path)
            state["current_format_path"] = init_path
            state["current_format_title"] = data.get("title", os.path.splitext(os.path.basename(init_path))[0])
            state["req_total_len"] = int(data.get("total_len", sum(int(it.get("length", 1)) for it in data.get("items", []))))
            state["items"] = [dict(it) for it in data.get("items", [])]
        except Exception:
            state["items"] = []
    else:
        state["current_format_title"] = "新規フォーマット"
        state["items"] = []

    # フォーマット選択ドロップダウンの先行定義
    preset_dropdown = ft.Dropdown(
        label="フォーマット選択",
        width=420,
        dense=True,
    )

    def rebuild_format_dropdown():
        """設定ファイルに指定された件数分、最近使用した順にフォーマット一覧を表示"""
        recent_formats = converter_core.get_recent_formats(state["config"])
        options = []
        for fpath, title in recent_formats:
            options.append(ft.dropdown.Option(fpath, title))
        preset_dropdown.options = options
        
        valid_keys = [opt.key for opt in options]
        if state["current_format_path"] in valid_keys:
            preset_dropdown.value = state["current_format_path"]
        elif valid_keys:
            preset_dropdown.value = valid_keys[0]

    def load_format(file_path: str, record_recent: bool = True) -> bool:
        """指定したフォーマットファイル（1フォーマット1ファイル）をロード"""
        try:
            data = converter_core.load_format_file(file_path)
            state["current_format_path"] = file_path
            state["current_format_title"] = data.get("title", os.path.splitext(os.path.basename(file_path))[0])
            state["req_total_len"] = int(data.get("total_len", sum(int(it.get("length", 1)) for it in data.get("items", []))))
            
            items_copy = []
            for it in data.get("items", []):
                items_copy.append(dict(it))
            state["items"] = items_copy

            if record_recent:
                converter_core.update_recent_format(file_path, state["config"])
            
            rebuild_format_dropdown()

            # CSVがすでに読み込まれている場合のマッピング再割り当て
            if state["csv_headers"]:
                if not state["has_header"]:
                    converter_core.map_columns_sequentially(state["items"], state["csv_headers"])
                else:
                    converter_core.auto_map_columns(state["csv_col_choices"], state["items"])

            refresh_mapping_editor()
            return True
        except Exception as ex:
            show_snack(f"フォーマット読込失敗: {str(ex)}", is_error=True)
            return False

    # --- UI更新用コールバック関数群 ---
    def update_status_bar():
        req_len = state.get("req_total_len", 0)
        curr_len = sum(int(it.get("length", 1)) for it in state["items"])
        
        status_len_text.value = f"レコード長: {curr_len} バイト"
        if req_len > 0:
            if curr_len == req_len:
                status_len_badge.bgcolor = ft.Colors.GREEN_100
                status_len_text.color = ft.Colors.GREEN_800
                status_len_text.value += f" (仕様: {req_len}B 一致 ✔)"
            else:
                diff = curr_len - req_len
                diff_str = f"+{diff}" if diff > 0 else f"{diff}"
                status_len_badge.bgcolor = ft.Colors.RED_100
                status_len_text.color = ft.Colors.RED_800
                status_len_text.value += f" (仕様: {req_len}B / 不一致 {diff_str}B ⚠)"
        else:
            status_len_badge.bgcolor = ft.Colors.BLUE_50
            status_len_text.color = ft.Colors.BLUE_900

        item_count_text.value = f"項目数: {len(state['items'])} 件"
        page.update()

    def refresh_csv_tab():
        if state["csv_path"]:
            csv_file_name_text.value = os.path.basename(state["csv_path"])
            csv_file_path_text.value = state["csv_path"]
            header_status_label = "【ヘッダーあり】1行目を列名として読込" if state["has_header"] else "【ヘッダーなし】1行目からデータとして読込"
            csv_rows_info_text.value = f"全 {state['csv_total_rows']} 行 | 列数: {len(state['csv_headers'])} 列 | {header_status_label}"
            csv_info_card.visible = True

            # DataTable更新
            display_headers = state["csv_headers"][:15]
            data_columns = []
            for h in display_headers:
                # 表示ラベル検索
                label = h
                for k, lbl in state["csv_col_choices"]:
                    if k == h:
                        label = lbl
                        break
                data_columns.append(ft.DataColumn(ft.Text(label, weight="bold", size=11)))
            
            if not data_columns:
                data_columns = [ft.DataColumn(ft.Text("項目"))]

            data_rows = []
            for row in state["csv_samples"][:10]:
                cells = [ft.DataCell(ft.Text(str(row.get(h, "")), size=11)) for h in display_headers]
                if cells:
                    data_rows.append(ft.DataRow(cells=cells))
            
            csv_data_table.columns = data_columns
            csv_data_table.rows = data_rows
            csv_table_container.visible = True
            no_csv_prompt.visible = False
            auto_map_btn.disabled = False
            seq_map_btn.disabled = False
        else:
            csv_info_card.visible = False
            csv_table_container.visible = False
            no_csv_prompt.visible = True
            auto_map_btn.disabled = True
            seq_map_btn.disabled = True
        page.update()

    def refresh_mapping_editor():
        mapping_list_view.controls.clear()
        
        curr_start = 1
        for idx, item in enumerate(state["items"]):
            length = int(item.get("length", 1))
            end_col = curr_start + length - 1
            item["start_col"] = curr_start

            row_ctrl = create_mapping_row_control(idx, item, curr_start, end_col)
            mapping_list_view.controls.append(row_ctrl)
            curr_start = end_col + 1

        update_status_bar()
        refresh_preview_tab()

    def refresh_preview_tab():
        if not state["output_path"] and state["csv_path"]:
            base, _ = os.path.splitext(state["csv_path"])
            state["output_path"] = f"{base}_固定長.txt"
            output_path_input.value = state["output_path"]

        if state["csv_samples"] and state["items"]:
            try:
                preview_lines = converter_core.generate_preview_lines(state["csv_samples"], state["items"], max_rows=5)
                preview_texts = []
                for i, (text, b_len) in enumerate(preview_lines):
                    preview_texts.append(f"[{i+1}行目: {b_len} Bytes]\n{text}")
                preview_display.value = ("\n" + ("-" * 80) + "\n").join(preview_texts)
                convert_exec_button.disabled = False
                preview_warning_banner.visible = False
            except Exception as ex:
                preview_display.value = f"プレビュー生成エラー: {str(ex)}"
                preview_warning_banner.visible = True
                convert_exec_button.disabled = True
        else:
            preview_display.value = "CSVファイルを選択すると、ここに固定長テキストのリアルタイム変換プレビューが表示されます。"
            convert_exec_button.disabled = not (state["csv_path"] and state["items"])
        page.update()

    # --- マッピング行UI生成 ---
    def create_mapping_row_control(idx: int, item: Dict[str, Any], start_col: int, end_col: int):
        pos_badge = ft.Container(
            content=ft.Text(f"#{idx+1}\n[{start_col}-{end_col}]", size=10, text_align=ft.TextAlign.CENTER, color=ft.Colors.GREY_700),
            width=65,
            alignment=ft.alignment.center
        )

        name_field = ft.TextField(
            value=item.get("name", ""),
            dense=True,
            width=170,
            text_size=12,
            tooltip=item.get("guide", "出力項目名"),
            on_change=lambda e, it=item: on_name_change(e, it)
        )

        len_field = ft.TextField(
            value=str(item.get("length", 1)),
            dense=True,
            width=55,
            text_size=12,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.RIGHT,
            on_change=lambda e, it=item: on_len_change(e, it)
        )

        # マッピング種別ドロップダウン
        map_type_drop = ft.Dropdown(
            value=item.get("mapping_type", "csv"),
            width=115,
            dense=True,
            text_size=11,
            options=[ft.dropdown.Option(k, v) for k, v in converter_core.MAPPING_TYPE_OPTIONS],
        )

        # CSV列選択ドロップダウン
        csv_options = [ft.dropdown.Option("", "-- 選択 --")]
        if state["csv_col_choices"]:
            for key, label in state["csv_col_choices"]:
                csv_options.append(ft.dropdown.Option(key, label))
        elif state["csv_headers"]:
            for h in state["csv_headers"]:
                csv_options.append(ft.dropdown.Option(h, h))

        # 現在の値が選択肢にあるか確認
        curr_val = item.get("csv_col", "")
        valid_val = curr_val if any(opt.key == curr_val for opt in csv_options) else ""

        csv_col_drop = ft.Dropdown(
            value=valid_val,
            width=175,
            dense=True,
            text_size=11,
            options=csv_options,
            visible=(item.get("mapping_type") == "csv")
        )

        const_val_input = ft.TextField(
            value=item.get("const_val", ""),
            hint_text="固定値テキスト",
            width=175,
            dense=True,
            text_size=11,
            visible=(item.get("mapping_type") == "const")
        )

        # パディングドロップダウン
        pad_drop = ft.Dropdown(
            value=item.get("pad", "left_space"),
            width=165,
            dense=True,
            text_size=11,
            options=[ft.dropdown.Option(k, v) for k, v in converter_core.PADDING_OPTIONS],
        )

        # 変換ドロップダウン
        transform_drop = ft.Dropdown(
            value=item.get("transform", "none"),
            width=165,
            dense=True,
            text_size=11,
            options=[ft.dropdown.Option(k, v) for k, v in converter_core.TRANSFORM_OPTIONS],
        )

        # 操作ボタン
        up_btn = ft.IconButton(
            icon=ft.Icons.ARROW_UPWARD,
            icon_size=16,
            tooltip="上へ移動",
            on_click=lambda _, i=idx: move_item(i, -1),
            disabled=(idx == 0)
        )
        down_btn = ft.IconButton(
            icon=ft.Icons.ARROW_DOWNWARD,
            icon_size=16,
            tooltip="下へ移動",
            on_click=lambda _, i=idx: move_item(i, 1),
            disabled=(idx == len(state["items"]) - 1)
        )
        del_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_color=ft.Colors.RED_400,
            icon_size=16,
            tooltip="削除",
            on_click=lambda _, i=idx: delete_item(i)
        )

        def on_map_type_change(e):
            item["mapping_type"] = map_type_drop.value
            csv_col_drop.visible = (map_type_drop.value == "csv")
            const_val_input.visible = (map_type_drop.value == "const")
            page.update()
            refresh_preview_tab()

        map_type_drop.on_change = on_map_type_change
        csv_col_drop.on_change = lambda e: on_field_change(item, "csv_col", csv_col_drop.value)
        const_val_input.on_change = lambda e: on_field_change(item, "const_val", const_val_input.value)
        pad_drop.on_change = lambda e: on_field_change(item, "pad", pad_drop.value)
        transform_drop.on_change = lambda e: on_field_change(item, "transform", transform_drop.value)

        # 主傷病名などの重要項目は背景を薄く強調
        is_shobyo = "主傷病名" in item.get("name", "")
        row_bg = ft.Colors.AMBER_50 if is_shobyo else (ft.Colors.GREY_50 if idx % 2 == 0 else ft.Colors.WHITE)

        row = ft.Container(
            content=ft.Row(
                controls=[
                    pos_badge,
                    name_field,
                    len_field,
                    map_type_drop,
                    ft.Stack([csv_col_drop, const_val_input], width=175),
                    pad_drop,
                    transform_drop,
                    ft.Row([up_btn, down_btn, del_btn], spacing=0)
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER
            ),
            padding=ft.padding.symmetric(vertical=2, horizontal=6),
            border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.GREY_200)),
            bgcolor=row_bg
        )
        return row

    def on_name_change(e, item):
        item["name"] = e.control.value

    def on_len_change(e, item):
        try:
            val = int(e.control.value)
            item["length"] = max(1, val)
        except ValueError:
            pass
        refresh_mapping_editor()

    def on_field_change(item, key, val):
        item[key] = val
        refresh_preview_tab()

    def move_item(index: int, direction: int):
        new_index = index + direction
        if 0 <= new_index < len(state["items"]):
            state["items"][index], state["items"][new_index] = state["items"][new_index], state["items"][index]
            refresh_mapping_editor()

    def delete_item(index: int):
        if len(state["items"]) > 1:
            state["items"].pop(index)
            refresh_mapping_editor()

    def add_new_item(e):
        new_item = {
            "start_col": sum(int(it.get("length", 1)) for it in state["items"]) + 1,
            "length": 10,
            "name": f"新規項目_{len(state['items'])+1}",
            "pad": "left_space",
            "val_type": "text",
            "guide": "",
            "mapping_type": "csv",
            "csv_col": state["csv_headers"][0] if state["csv_headers"] else "",
            "const_val": "",
            "transform": "none"
        }
        state["items"].append(new_item)
        refresh_mapping_editor()

    def on_preset_change(e):
        selected_path = preset_dropdown.value
        if selected_path and selected_path != state["current_format_path"]:
            if load_format(selected_path, record_recent=True):
                show_snack(f"フォーマット「{state['current_format_title']}」を選択しました")

    def on_auto_map_click(e):
        if not state["csv_headers"]:
            show_snack("CSVファイルを先に選択してください", is_error=True)
            return
        matched = converter_core.auto_map_columns(state["csv_col_choices"], state["items"])
        refresh_mapping_editor()
        show_snack(f"列名から推測: {matched} 項目を割り当てました！")

    def on_seq_map_click(e):
        if not state["csv_headers"]:
            show_snack("CSVファイルを先に選択してください", is_error=True)
            return
        matched = converter_core.map_columns_sequentially(state["items"], state["csv_headers"])
        refresh_mapping_editor()
        show_snack(f"順序マッピング: 左から順に {matched} 項目を1対1で割り当てました！")

    def show_snack(msg: str, is_error: bool = False):
        snack = ft.SnackBar(
            content=ft.Text(msg, color=ft.Colors.WHITE),
            bgcolor=ft.Colors.RED_600 if is_error else ft.Colors.GREEN_700,
            duration=3500
        )
        page.overlay.append(snack)
        snack.open = True
        page.update()

    # --- CSVファイルピッカー処理 ---
    def on_csv_file_picked(e: ft.FilePickerResultEvent):
        if not e.files:
            return
        file_path = e.files[0].path
        load_csv_file(file_path, has_header_override=None)

    def load_csv_file(file_path: str, has_header_override: Optional[bool] = None):
        if not os.path.exists(file_path):
            alt_path = file_path.replace("strage", "storage")
            if os.path.exists(alt_path):
                file_path = alt_path

        try:
            headers, samples, total, detected_has_header, col_choices = converter_core.read_csv_samples(
                file_path,
                encoding=state["csv_encoding"],
                has_header=has_header_override
            )
            state["csv_path"] = file_path
            state["csv_headers"] = headers
            state["csv_samples"] = samples
            state["csv_total_rows"] = total
            state["has_header"] = detected_has_header
            state["csv_col_choices"] = col_choices
            
            # チェックボックスのUIを更新
            header_checkbox.value = detected_has_header
            
            # 出力先パス自動設定
            base, _ = os.path.splitext(file_path)
            state["output_path"] = f"{base}_固定長.txt"
            output_path_input.value = state["output_path"]

            # マッピングの自動割り当て
            if not detected_has_header:
                # ヘッダーなしCSVの場合は順番通りに1対1マッピングを適用！
                matched = converter_core.map_columns_sequentially(state["items"], headers)
                map_msg = f"（ヘッダーなしCSVのため左から順に {matched} 項目を自動1対1マッピング）"
            else:
                matched = converter_core.auto_map_columns(col_choices, state["items"])
                map_msg = f"（列名から {matched} 項目を自動推測マッピング）"
            
            refresh_csv_tab()
            refresh_mapping_editor()
            show_snack(f"CSV読込完了: {total} 行取得 {map_msg}")
        except Exception as ex:
            show_snack(f"CSV読み込み失敗: {str(ex)}", is_error=True)

    def on_header_checkbox_change(e):
        if not state["csv_path"]:
            return
        new_val = header_checkbox.value
        load_csv_file(state["csv_path"], has_header_override=new_val)

    def load_sample_csv(e):
        formats_dir = state["config"].get("formats_directory", "formats")
        preset_file = os.path.join(formats_dir, "hosp_in_odd.json")
        if os.path.exists(preset_file):
            load_format(preset_file, record_recent=True)
        sample_path = os.path.abspath("sample_hospital_inpatient.csv")
        if not os.path.exists(sample_path):
            import create_sample
            create_sample.create_sample_csv(sample_path)
        load_csv_file(sample_path, has_header_override=True)

    def load_outpatient_csv(e):
        formats_dir = state["config"].get("formats_directory", "formats")
        preset_file = os.path.join(formats_dir, "hosp_out_odd.json")
        if os.path.exists(preset_file):
            load_format(preset_file, record_recent=True)
        out_csv = os.path.abspath("storage/data/〇患者調査‗病院外来（奇数）票.csv")
        if os.path.exists(out_csv):
            load_csv_file(out_csv, has_header_override=None)

    # --- フォーマット設定の保存・読込 ---
    def open_save_dialog(e):
        """特定フォルダ（formats_directory）へ1フォーマット1ファイルとして保存するダイアログ"""
        formats_dir = state["config"].get("formats_directory", "formats")
        default_name = ""
        if state["current_format_path"]:
            default_name = os.path.basename(state["current_format_path"])
        if not default_name or default_name in ("presets_r8.json", "presets.json"):
            default_name = "custom_format.json"

        title_field = ft.TextField(
            label="フォーマット名 (タイトル)",
            value=state["current_format_title"] or "新規固定長フォーマット",
            width=380,
            dense=True
        )
        filename_field = ft.TextField(
            label="保存ファイル名 (.json)",
            value=default_name,
            width=380,
            dense=True
        )
        folder_info = ft.Text(
            f"保存先フォルダ: {os.path.abspath(formats_dir)}",
            size=11,
            color=ft.Colors.GREY_600
        )

        def do_save(ev):
            raw_name = filename_field.value.strip()
            if not raw_name:
                show_snack("ファイル名を入力してください", is_error=True)
                return
            if not raw_name.lower().endswith(".json"):
                raw_name += ".json"

            target_path = os.path.join(formats_dir, raw_name)
            new_title = title_field.value.strip() or os.path.splitext(raw_name)[0]

            try:
                converter_core.save_format_file(target_path, new_title, state["items"])
                load_format(target_path, record_recent=True)
                page.close(save_dlg)
                show_snack(f"フォーマット設定を保存しました: {raw_name}")
            except Exception as ex:
                show_snack(f"設定保存失敗: {str(ex)}", is_error=True)

        def open_external_picker(ev):
            page.close(save_dlg)
            raw_name = filename_field.value.strip() or "custom_format.json"
            if not raw_name.lower().endswith(".json"):
                raw_name += ".json"
            save_config_picker.save_file(file_name=raw_name, file_type="json")

        save_dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.Icons.SAVE, color=ft.Colors.BLUE_600),
                ft.Text("フォーマット設定の保存", weight="bold")
            ], spacing=8),
            content=ft.Column([
                ft.Text("現在のマッピング設定を1フォーマット1ファイルとして特定フォルダに保存します。", size=12),
                title_field,
                filename_field,
                folder_info
            ], spacing=12, tight=True, width=420),
            actions=[
                ft.TextButton("別フォルダへ保存...", on_click=open_external_picker, tooltip="任意のフォルダを選択して保存"),
                ft.TextButton("キャンセル", on_click=lambda ev: page.close(save_dlg)),
                ft.ElevatedButton("保存", bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE, on_click=do_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(save_dlg)

    def on_save_config_result(e: ft.FilePickerResultEvent):
        if not e.path:
            return
        try:
            title = state["current_format_title"] or os.path.splitext(os.path.basename(e.path))[0]
            converter_core.save_format_file(e.path, title, state["items"])
            load_format(e.path, record_recent=True)
            show_snack(f"フォーマット設定を保存しました: {os.path.basename(e.path)}")
        except Exception as ex:
            show_snack(f"設定保存失敗: {str(ex)}", is_error=True)

    def on_load_config_result(e: ft.FilePickerResultEvent):
        if not e.files:
            return
        picked_path = e.files[0].path
        if load_format(picked_path, record_recent=True):
            show_snack(f"フォーマット設定を読み込みました: {os.path.basename(picked_path)}")

    # --- 固定長変換の実行 ---
    def on_convert_click(e):
        if not state["csv_path"]:
            show_snack("元となるCSVデータを選択してください", is_error=True)
            return
        
        out_path = output_path_input.value.strip()
        if not out_path:
            show_snack("出力先ファイルパスを指定してください", is_error=True)
            return

        convert_progress_bar.visible = True
        convert_result_box.visible = False
        page.update()

        try:
            res = converter_core.execute_batch_conversion(
                csv_path=state["csv_path"],
                output_path=out_path,
                items=state["items"],
                csv_encoding=state["csv_encoding"],
                output_newline="\r\n",
                has_header=state["has_header"]
            )
            convert_progress_bar.visible = False
            convert_result_box.visible = True
            result_details_text.value = (
                f"✔ 正常に出力完了しました！\n"
                f"・出力先ファイル: {res['output_path']}\n"
                f"・変換レコード数: {res['rows_converted']} 行\n"
                f"・1レコード長: {res['line_bytes']} バイト (改行 CRLF 込: {res['line_bytes']+2}B)\n"
                f"・総ファイルサイズ: {res['total_file_bytes']:,} バイト\n"
                f"・パディング埋めやデータ変換ルールを保持して正常に出力完了しました。"
            )
            page.update()
            show_snack(f"変換完了: {res['rows_converted']} 件出力")
        except Exception as ex:
            convert_progress_bar.visible = False
            convert_result_box.visible = True
            result_details_text.value = f"❌ エラーが発生しました:\n{traceback.format_exc()}"
            page.update()
            show_snack(f"変換エラー: {str(ex)}", is_error=True)

    # --- ファイルピッカー登録 ---
    csv_file_picker = ft.FilePicker(on_result=on_csv_file_picked)
    save_config_picker = ft.FilePicker(on_result=on_save_config_result)
    load_config_picker = ft.FilePicker(on_result=on_load_config_result)
    page.overlay.extend([csv_file_picker, save_config_picker, load_config_picker])

    # ================= UIコンポーネントの構築 =================
    # --- 1. トップバー ---
    preset_dropdown.on_change = on_preset_change

    save_config_btn = ft.ElevatedButton(
        "設定保存",
        icon=ft.Icons.SAVE,
        tooltip="現在のフォーマット設定をJSONファイルに保存",
        on_click=open_save_dialog
    )

    load_config_btn = ft.ElevatedButton(
        "設定読込",
        icon=ft.Icons.FOLDER_OPEN,
        tooltip="保存したフォーマットJSONファイルを読み込む",
        on_click=lambda _: load_config_picker.pick_files(allowed_extensions=["json"])
    )

    top_bar = ft.Container(
        content=ft.Row(
            controls=[
                ft.Row([
                    ft.Icon(ft.Icons.AUTO_AWESOME, color=ft.Colors.BLUE_600, size=28),
                    ft.Column([
                        ft.Text("DataMagician", size=18, weight="bold"),
                        ft.Text("CSV ➔ 固定長テキスト変換ツール", size=11, color=ft.Colors.GREY_600),
                    ], spacing=1)
                ]),
                ft.Row([
                    preset_dropdown,
                    load_config_btn,
                    save_config_btn
                ], spacing=10)
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        ),
        padding=10,
        border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.GREY_300))
    )

    # --- 2. ステータスバー ---
    status_len_text = ft.Text("レコード長: 177 バイト", size=13, weight="bold")
    status_len_badge = ft.Container(
        content=status_len_text,
        padding=ft.padding.symmetric(horizontal=12, vertical=6),
        border_radius=6,
        bgcolor=ft.Colors.GREEN_100
    )
    item_count_text = ft.Text("項目数: 50 件", size=13, color=ft.Colors.GREY_700)
    
    auto_map_btn = ft.ElevatedButton(
        "列名から推測マッピング",
        icon=ft.Icons.AUTO_FIX_HIGH,
        bgcolor=ft.Colors.AMBER_700,
        color=ft.Colors.WHITE,
        disabled=True,
        tooltip="CSVの列名（ヘッダー）と出力項目名を自動マッチングします",
        on_click=on_auto_map_click
    )

    seq_map_btn = ft.ElevatedButton(
        "左から順に1対1マッピング",
        icon=ft.Icons.FORMAT_LIST_NUMBERED,
        bgcolor=ft.Colors.TEAL_700,
        color=ft.Colors.WHITE,
        disabled=True,
        tooltip="CSVの列順が出力項目の順序になっている場合に、順番通りに一括マッピングします",
        on_click=on_seq_map_click
    )

    add_item_btn = ft.OutlinedButton(
        "項目追加",
        icon=ft.Icons.ADD,
        on_click=add_new_item
    )

    mapping_toolbar = ft.Container(
        content=ft.Row(
            controls=[
                ft.Row([status_len_badge, item_count_text], spacing=15),
                ft.Row([seq_map_btn, auto_map_btn, add_item_btn], spacing=10)
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        ),
        padding=ft.padding.symmetric(vertical=8, horizontal=12),
        bgcolor=ft.Colors.GREY_100,
        border_radius=8
    )

    # --- タブ1: 入力CSV設定 & プレビュー ---
    csv_file_name_text = ft.Text(size=14, weight="bold")
    csv_file_path_text = ft.Text(size=11, color=ft.Colors.GREY_600)
    csv_rows_info_text = ft.Text(size=12, color=ft.Colors.BLUE_800)

    header_checkbox = ft.Checkbox(
        label="先頭行はヘッダー（列名）である",
        value=True,
        tooltip="チェックを外すと、1行目もデータレコードとして読み込み、列を[1]列1, [2]列2...として扱います",
        on_change=on_header_checkbox_change
    )

    csv_info_card = ft.Card(
        content=ft.Container(
            content=ft.Column([
                csv_file_name_text,
                csv_file_path_text,
                csv_rows_info_text,
                header_checkbox
            ], spacing=4),
            padding=12
        ),
        visible=False
    )

    csv_data_table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("項目"))],
        rows=[],
        border=ft.border.all(1, ft.Colors.GREY_300),
        vertical_lines=ft.border.all(1, ft.Colors.GREY_200),
        horizontal_lines=ft.border.all(1, ft.Colors.GREY_200),
        heading_row_color=ft.Colors.BLUE_50,
        heading_row_height=36,
        data_row_min_height=32,
        data_row_max_height=36
    )

    csv_table_container = ft.Container(
        content=ft.Column([
            ft.Text("CSV先頭データプレビュー（先頭10行）", size=13, weight="bold"),
            ft.Row([csv_data_table], scroll=ft.ScrollMode.ALWAYS)
        ], spacing=8),
        visible=False
    )

    no_csv_prompt = ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.UPLOAD_FILE, size=48, color=ft.Colors.GREY_400),
            ft.Text("元となるCSVファイルを選択してください", size=14, color=ft.Colors.GREY_600),
            ft.Row([
                ft.ElevatedButton("CSVファイルを選択", icon=ft.Icons.FILE_OPEN, bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE, on_click=lambda _: csv_file_picker.pick_files(allowed_extensions=["csv"])),
                ft.OutlinedButton("サンプルCSV（入院）", icon=ft.Icons.LIGHTBULB_OUTLINE, on_click=load_sample_csv),
                ft.OutlinedButton("外来（奇数）票CSV", icon=ft.Icons.FOLDER_SPECIAL, on_click=load_outpatient_csv),
            ], alignment=ft.MainAxisAlignment.CENTER)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
        alignment=ft.alignment.center,
        padding=40,
        border=ft.border.all(2, ft.Colors.GREY_300),
        border_radius=10
    )

    tab_csv = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.ElevatedButton("CSVファイルを選択", icon=ft.Icons.FILE_OPEN, bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE, on_click=lambda _: csv_file_picker.pick_files(allowed_extensions=["csv"])),
                ft.OutlinedButton("サンプルCSV（入院）", icon=ft.Icons.LIGHTBULB_OUTLINE, on_click=load_sample_csv),
                ft.OutlinedButton("外来（奇数）票CSV", icon=ft.Icons.FOLDER_SPECIAL, on_click=load_outpatient_csv),
                ft.Dropdown(
                    label="CSV文字コード",
                    value="cp932",
                    width=180,
                    dense=True,
                    options=[
                        ft.dropdown.Option("cp932", "Shift-JIS / CP932"),
                        ft.dropdown.Option("utf-8-sig", "UTF-8 (BOM有)"),
                        ft.dropdown.Option("utf-8", "UTF-8"),
                    ],
                    on_change=lambda e: [state.update({"csv_encoding": e.control.value}), load_csv_file(state["csv_path"], state["has_header"]) if state["csv_path"] else None]
                )
            ], spacing=15),
            csv_info_card,
            no_csv_prompt,
            csv_table_container
        ], spacing=15, scroll=ft.ScrollMode.AUTO),
        padding=15
    )

    # --- タブ2: マッピング & 変換設定 ---
    mapping_list_header = ft.Container(
        content=ft.Row([
            ft.Text("位置", width=65, weight="bold", size=12),
            ft.Text("出力項目名", width=170, weight="bold", size=12),
            ft.Text("桁数(B)", width=55, weight="bold", size=12, text_align=ft.TextAlign.RIGHT),
            ft.Text("種別", width=115, weight="bold", size=12),
            ft.Text("マッピング元 (CSV列 / 固定値)", width=175, weight="bold", size=12),
            ft.Text("パディング埋め文字", width=165, weight="bold", size=12),
            ft.Text("データ変換ルール", width=165, weight="bold", size=12),
            ft.Text("操作", width=100, weight="bold", size=12),
        ]),
        padding=ft.padding.symmetric(vertical=8, horizontal=6),
        bgcolor=ft.Colors.BLUE_GREY_100,
        border_radius=5
    )

    mapping_list_view = ft.ListView(
        spacing=0,
        expand=True,
        divider_thickness=1
    )

    tab_mapping = ft.Container(
        content=ft.Column([
            mapping_toolbar,
            mapping_list_header,
            ft.Container(content=mapping_list_view, expand=True)
        ], expand=True, spacing=10),
        padding=10,
        expand=True
    )

    # --- タブ3: 出力プレビュー & 変換実行 ---
    output_path_input = ft.TextField(
        label="固定長テキスト出力先ファイルパス",
        value="",
        expand=True,
        dense=True
    )

    preview_warning_banner = ft.Banner(
        bgcolor=ft.Colors.AMBER_100,
        leading=ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.AMBER_900, size=32),
        content=ft.Text("CSVの列がマッピングされていない項目があります。固定値または空白として出力されます。", color=ft.Colors.AMBER_900),
        actions=[ft.TextButton("確認した", on_click=lambda _: [setattr(preview_warning_banner, 'visible', False), page.update()])]
    )

    ruler_text = "----+----10---+----20---+----30---+----40---+----50---+----60---+----70---+----80---+----90---+---100---+---110---+---120---+---130---+---140---+---150---+---160---+---170---+---180---+---190---+---200---+---210---+---220---+---230---+---240---+---250---+---260---+---270---+---280"
    
    preview_display = ft.TextField(
        multiline=True,
        read_only=True,
        text_style=ft.TextStyle(font_family="monospace", size=12),
        min_lines=10,
        max_lines=15,
        expand=True
    )

    convert_exec_button = ft.ElevatedButton(
        "固定長テキストファイルへ変換実行",
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        bgcolor=ft.Colors.GREEN_700,
        color=ft.Colors.WHITE,
        height=48,
        on_click=on_convert_click,
        disabled=True
    )

    convert_progress_bar = ft.ProgressBar(visible=False, color=ft.Colors.GREEN_600)
    result_details_text = ft.Text(size=13, weight="bold")
    convert_result_box = ft.Container(
        content=result_details_text,
        bgcolor=ft.Colors.GREEN_50,
        border=ft.border.all(1, ft.Colors.GREEN_400),
        padding=15,
        border_radius=8,
        visible=False
    )

    tab_preview = ft.Container(
        content=ft.Column([
            ft.Row([output_path_input]),
            ft.Text("固定長出力リアルタイムプレビュー (Shift-JIS / CP932):", size=13, weight="bold"),
            ft.Container(
                content=ft.Text(ruler_text, font_family="monospace", size=11, color=ft.Colors.BLUE_900),
                bgcolor=ft.Colors.BLUE_50,
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                border_radius=4
            ),
            preview_display,
            ft.Divider(),
            ft.Row([convert_exec_button], alignment=ft.MainAxisAlignment.CENTER),
            convert_progress_bar,
            convert_result_box
        ], spacing=10, scroll=ft.ScrollMode.AUTO),
        padding=15
    )

    # --- メインタブの組み立て ---
    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=200,
        tabs=[
            ft.Tab(text="1. 入力CSV設定 & プレビュー", icon=ft.Icons.SOURCE, content=tab_csv),
            ft.Tab(text="2. 出力項目マッピング (DataMagic風)", icon=ft.Icons.RULE, content=tab_mapping),
            ft.Tab(text="3. 固定長プレビュー & 変換実行", icon=ft.Icons.PREVIEW, content=tab_preview),
        ],
        expand=True
    )

    page.add(
        top_bar,
        tabs
    )

    # 初回描画
    rebuild_format_dropdown()
    refresh_csv_tab()
    refresh_mapping_editor()

if __name__ == "__main__":
    ft.app(target=main)
