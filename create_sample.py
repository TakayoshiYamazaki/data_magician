import csv
import os

def create_sample_csv(filename: str = "sample_hospital_inpatient.csv"):
    rows = [
        {
            "患者ID": "0045",
            "性別": "男",
            "生年月日": "1955-08-23",
            "都道府県": "東京都",
            "市郡": "新宿区",
            "区町村": "西新宿",
            "入院日": "2024-10-15",
            "受療種別": "1",
            "病名": "急性胆嚢炎",
            "紹介状況": "2",
            "病床区分": "5"
        },
        {
            "患者ID": "1208",
            "性別": "女",
            "生年月日": "1988-12-05",
            "都道府県": "埼玉県",
            "市郡": "さいたま市",
            "区町村": "大宮区",
            "入院日": "2024-10-20",
            "受療種別": "1",
            "病名": "２型糖尿病",
            "紹介状況": "8",
            "病床区分": "5"
        },
        {
            "患者ID": "3091",
            "性別": "女性",
            "生年月日": "2021-03-10",
            "都道府県": "神奈川県",
            "市郡": "横浜市",
            "区町村": "中区",
            "入院日": "2024-10-21",
            "受療種別": "1",
            "病名": "肺炎",
            "紹介状況": "1",
            "病床区分": "5"
        }
    ]
    with open(filename, "w", encoding="cp932", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Created {filename} with {len(rows)} sample records.")

if __name__ == "__main__":
    create_sample_csv()
