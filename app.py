from flask import Flask, request, render_template, jsonify
import requests
from datetime import datetime,timedelta
import calendar

import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# --- CẤU HÌNH NOTION CỦA BẠN ---
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
BOOKING_DB_ID = os.getenv("BOOKING_DB_ID")
EXPENSES_DB_ID = os.getenv("EXPENSES_DB_ID")
url = "https://api.notion.com/v1/pages"

headers = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# 1. Trang chủ (ĐÃ ĐƯỢC NÂNG CẤP ĐỂ TÍNH KPI)
@app.route('/')
def home():
    # Gọi API lấy dữ liệu Booking
    res_b = requests.post(f"https://api.notion.com/v1/databases/{BOOKING_DB_ID}/query", headers=headers)
    bookings_data = res_b.json().get('results', [])

    now = datetime.now()
    current_month = now.month
    current_year = now.year

    monthly_revenue = 0
    booked_hours = 0

    for b in bookings_data:
        props = b.get('properties', {})
        total = props.get('Total', {}).get('number', 0)
        checkin_str = props.get('Checkin', {}).get('date', {}).get('start')
        checkout_str = props.get('Checkout', {}).get('date', {}).get('start')

        if checkin_str and checkout_str:
            try:
                # Ép kiểu chuỗi ngày của Notion thành đối tượng Thời gian trong Python
                checkin_dt = datetime.fromisoformat(checkin_str.replace('Z', '+00:00'))
                checkout_dt = datetime.fromisoformat(checkout_str.replace('Z', '+00:00'))

                # CHỈ TÍNH NHỮNG BOOKING CÓ NGÀY CHECK-IN RỚT VÀO THÁNG HIỆN TẠI
                if checkin_dt.month == current_month and checkin_dt.year == current_year:
                    monthly_revenue += (total if total else 0)
                    
                    # Tính khoảng thời gian khách ở (tính bằng Giờ)
                    duration_seconds = (checkout_dt - checkin_dt).total_seconds()
                    duration_hours = duration_seconds / 3600
                    if duration_hours > 0:
                        booked_hours += duration_hours
            except Exception as e:
                continue

    # Tính Tỉ lệ trống (Vacancy Rate)
    # 1. Lấy số ngày của tháng hiện tại (vd: Tháng 4 là 30 ngày)
    days_in_month = calendar.monthrange(current_year, current_month)[1]
    # 2. Tổng số giờ tối đa có thể bán
    total_available_hours = days_in_month * 24
    
    # 3. Tính phần trăm
    if total_available_hours > 0:
        occupancy_rate = (booked_hours / total_available_hours) * 100
        vacancy_rate = 100 - occupancy_rate
    else:
        vacancy_rate = 100

    # Ép định dạng 1 chữ số thập phân (VD: 85.5%)
    formatted_vacancy = f"{vacancy_rate:.1f}%"

    # Trả 2 biến này ra cho file home.html hiển thị
    return render_template('home.html', 
                           kpi_monthly_revenue=format_vnd(monthly_revenue), 
                           kpi_vacancy_rate=formatted_vacancy)

# 2. Trang Nhập phòng mới
@app.route('/create')
def create_booking_page():
    return render_template('create.html')

# 3. Trang Lịch trống
@app.route('/availability')
def availability_page():
    return render_template('availability.html')

# MỘT HÀM NHỎ ĐỂ FORMAT TIỀN TỆ ĐẸP MẮT (100000 -> 100.000 ₫)
def format_vnd(amount):
    return f"{int(amount):,} ₫".replace(',', '.')

# 4. Trang Nhập Tiền Chi & Dashboard KPI (ĐÃ CÓ LỌC THÁNG)
@app.route('/expenses')
def expenses_page():
    # 1. Nhận tháng từ trình duyệt gửi lên, mặc định là tháng hiện tại (VD: 2026-04)
    selected_month = request.args.get('month')
    if not selected_month:
        selected_month = datetime.now().strftime('%Y-%m')

    transactions = [] 
    water_dates = []

    # BƯỚC A: LẤY TOÀN BỘ BOOKING (THU)
    res_b = requests.post(f"https://api.notion.com/v1/databases/{BOOKING_DB_ID}/query", headers=headers)
    bookings_data = res_b.json().get('results', [])
    
    for b in bookings_data:
        props = b.get('properties', {})
        page_id = b.get('id') 
        
        name_list = props.get('Name', {}).get('title', [])
        name = name_list[0].get('text', {}).get('content', 'Khách') if name_list else 'Khách'
        
        total = props.get('Total', {}).get('number', 0)
        checkin_full = props.get('Checkin', {}).get('date', {}).get('start', '')
        checkin_date = checkin_full[:10] if checkin_full else '1970-01-01'
        
        transactions.append({
            "id": page_id,
            "desc": f"Booking: {name}",
            "date": checkin_date,
            "amount": total if total else 0, # Giữ số thực để tính toán
            "amount_str": f"+ {format_vnd(total)}" if total else "+ 0 ₫",
            "type": "income",
            "raw_date": checkin_date 
        })

    # BƯỚC B: LẤY TOÀN BỘ TIỀN CHI (CHI)
    res_e = requests.post(f"https://api.notion.com/v1/databases/{EXPENSES_DB_ID}/query", headers=headers)
    expenses_data = res_e.json().get('results', [])
    
    for e in expenses_data:
        props = e.get('properties', {})
        page_id = e.get('id')
        
        amount = props.get('Amount', {}).get('number', 0)
        reason_list = props.get('Reason', {}).get('title', [])
        reason = reason_list[0].get('text', {}).get('content', 'Chi phí không tên') if reason_list else 'Chi phí không tên'
        
        date = props.get('Date', {}).get('date', {}).get('start', '')
        if not date: date = '1970-01-01'
        
        if '[💧 NƯỚC]' in reason and date != '1970-01-01':
            water_dates.append(date)

        transactions.append({
            "id": page_id,
            "desc": reason,
            "date": date,
            "amount": amount if amount else 0, # Giữ số thực để tính toán
            "amount_str": f"- {format_vnd(amount)}" if amount else "- 0 ₫",
            "type": "expense",
            "raw_date": date
        })

    # BƯỚC C: SẮP XẾP CHUNG THEO NGÀY
    transactions.sort(key=lambda x: x['raw_date'], reverse=True)

    # BƯỚC D: TÍNH TOÁN KPI NƯỚC (Dùng TẤT CẢ dữ liệu, vì nước mua tháng trước vẫn uống tháng này)
    if water_dates:
        water_dates.sort(reverse=True)
        last_water_date = water_dates[0]
    else:
        last_water_date = None

    bookings_since_water = 0
    if last_water_date:
        for t in transactions:
            if t['type'] == 'income' and t['raw_date'] != '1970-01-01' and t['raw_date'] >= last_water_date:
                bookings_since_water += 1
    else:
        bookings_since_water = len([t for t in transactions if t['type'] == 'income'])

    remaining_water = 25 - (bookings_since_water * 2)

    # BƯỚC E: LỌC DỮ LIỆU & TÍNH TÀI CHÍNH THEO THÁNG ĐƯỢC CHỌN
    filtered_transactions = []
    total_income = 0
    total_expenses = 0
    total_cleaning = 0

    for t in transactions:
        # Chỉ lấy những giao dịch có ngày bắt đầu bằng tháng được chọn (VD: "2026-04-15".startswith("2026-04"))
        if t['raw_date'].startswith(selected_month):
            filtered_transactions.append(t)
            if t['type'] == 'income':
                total_income += t['amount']
            else:
                total_expenses += t['amount']
                if "dọn phòng" in t['desc'].lower():
                    total_cleaning += t['amount']

    profit = total_income - total_expenses

    return render_template('expenses.html',
        selected_month=selected_month, # Truyền tháng đang chọn ra giao diện
        kpi_expenses=format_vnd(total_expenses),
        kpi_profit=format_vnd(profit),
        kpi_cleaning=format_vnd(total_cleaning),
        is_profit_positive=(profit >= 0),
        kpi_water=remaining_water,
        kpi_water_date=last_water_date if last_water_date else "Chưa ghi",
        transactions=filtered_transactions # Chỉ gửi danh sách của tháng này
    )

#5 
@app.route('/api/bookings')
def get_bookings():
    query_url = f"https://api.notion.com/v1/databases/{BOOKING_DB_ID}/query"
    res = requests.post(query_url, headers=headers)
    if res.status_code != 200:
        return jsonify({"error": "Không thể lấy dữ liệu từ Notion"}), 400

    notion_data = res.json()
    events = []
    for row in notion_data.get('results', []):
        props = row.get('properties', {})
        try:
            name_list = props.get('Name', {}).get('title', [])
            name = name_list[0].get('text', {}).get('content', 'Khách ẩn danh') if name_list else 'Khách ẩn danh'
            
            checkin = props.get('Checkin', {}).get('date', {}).get('start')
            checkout = props.get('Checkout', {}).get('date', {}).get('start')
            total = props.get('Total', {}).get('number', 0)
            
            if checkin and checkout:
                events.append({
                    "title": name,
                    "start": checkin,
                    "end": checkout,
                    "color": "#1e293b", 
                    "textColor": "#ffffff",
                    "extendedProps": {"total_amount": total}
                })
        except Exception as e:
            continue
    return jsonify(events)

# 6. Xử lý lưu Booking & Chống trùng giờ & Ghi nhận phí dọn dẹp
@app.route('/submit-booking', methods=['POST'])
def submit_booking():
    guest_name = request.form.get('guest_name')
    checkin_date = request.form.get('checkin_date')
    checkin_hour = request.form.get('checkin_hour')
    checkout_date = request.form.get('checkout_date')
    checkout_hour = request.form.get('checkout_hour')
    total_amount = request.form.get('total_amount')
    cleaning_fee = request.form.get('cleaning_fee') # Bắt giá trị checkbox

    checkin_iso = f"{checkin_date}T{checkin_hour}:00"
    checkout_iso = f"{checkout_date}T{checkout_hour}:00"

    # CHUYỂN STRING THÀNH ĐỐI TƯỢNG THỜI GIAN ĐỂ TÍNH TOÁN (Giữ nguyên múi giờ Local để check)
    try:
        new_start = datetime.strptime(checkin_iso, "%Y-%m-%dT%H:%M:%S")
        new_end = datetime.strptime(checkout_iso, "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return jsonify({"success": False, "error": "Định dạng ngày giờ không hợp lệ!"}), 400

    if new_start >= new_end:
        return jsonify({"success": False, "error": "Giờ Check-out phải nằm sau giờ Check-in!"}), 400

    # LẤY TOÀN BỘ BOOKING CŨ ĐỂ KIỂM TRA TRÙNG LỊCH
    res_b = requests.post(f"https://api.notion.com/v1/databases/{BOOKING_DB_ID}/query", headers=headers)
    bookings_data = res_b.json().get('results', [])

    for b in bookings_data:
        props = b.get('properties', {})
        ex_checkin_str = props.get('Checkin', {}).get('date', {}).get('start', '')[:19]
        ex_checkout_str = props.get('Checkout', {}).get('date', {}).get('start', '')[:19]

        if ex_checkin_str and ex_checkout_str:
            try:
                # Xử lý format ngày của Notion (có thể chỉ có ngày hoặc có cả giờ)
                if len(ex_checkin_str) == 10:
                    ex_start = datetime.strptime(ex_checkin_str, "%Y-%m-%d")
                    ex_end = datetime.strptime(ex_checkout_str, "%Y-%m-%d")
                else:
                    ex_start = datetime.strptime(ex_checkin_str, "%Y-%m-%dT%H:%M:%S")
                    ex_end = datetime.strptime(ex_checkout_str, "%Y-%m-%dT%H:%M:%S")

                # 1. KIỂM TRA TRÙNG LỊCH THỰC TẾ (Đè lên nhau trong lúc ở)
                if new_start < ex_end and ex_start < new_end:
                    overlap_time = f"Từ {ex_start.strftime('%H:%M %d/%m')} đến {ex_end.strftime('%H:%M %d/%m')}"
                    return jsonify({
                        "success": False, 
                        "error": f"Trùng lịch rùi ní ơi ! Có khách đặt {overlap_time}"
                    }), 400
                
                # 2. KIỂM TRA VƯỚNG DỌN PHÒNG CỦA KHÁCH TRƯỚC (Khách cũ out chưa đủ 1 tiếng)
                elif ex_end <= new_start < (ex_end + timedelta(hours=1)):
                    return jsonify({
                        "success": False, 
                        "error": "Bị vướng dọn phòng của booking trước rồi ní"
                    }), 400
                
                # 3. KIỂM TRA VƯỚNG DỌN PHÒNG CHO KHÁCH SAU (Khách mới out chưa kịp dọn cho khách kế)
                elif new_end <= ex_start < (new_end + timedelta(hours=1)):
                    return jsonify({
                        "success": False, 
                        "error": "Bị vướng thời gian dọn phòng cho khách sau rồi ní"
                    }), 400

            except Exception:
                continue

    # NẾU KHÔNG TRÙNG -> LƯU BOOKING VÀO NOTION
    data_booking = {
        "parent": {"database_id": BOOKING_DB_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": guest_name}}]},
            
            # ĐÃ SỬA Ở ĐÂY: Thêm +07:00 vào đuôi để Notion hiểu đây là giờ Việt Nam
            "Checkin": {"date": {"start": f"{checkin_iso}+07:00"}},
            "Checkout": {"date": {"start": f"{checkout_iso}+07:00"}},
            
            "Total": {"number": int(total_amount)}
        }
    }
    
    res = requests.post(url, headers=headers, json=data_booking)
    if res.status_code != 200:
        return jsonify({"success": False, "error": "Lỗi lưu Booking: " + res.text}), 400

    # NẾU CÓ ĐÁNH DẤU CHECKBOX DỌN PHÒNG -> TỰ ĐỘNG THÊM VÀO SỔ CHI PHÍ
    if cleaning_fee == 'yes':
        data_expense = {
            "parent": {"database_id": EXPENSES_DB_ID},
            "properties": {
                "Reason": {"title": [{"text": {"content": f"[🧹 DỌN PHÒNG] Khách {guest_name}"}}]},
                "Date": {"date": {"start": checkin_date}},
                "Amount": {"number": 50000}
            }
        }
        requests.post(url, headers=headers, json=data_expense) # Gửi ngầm không cần check lỗi

    return jsonify({"success": True})

@app.route('/submit-expense', methods=['POST'])
def submit_expense():
    reason = request.form.get('reason')
    date = request.form.get('date')
    amount = request.form.get('amount')
    bought_water = request.form.get('bought_water')

    if bought_water == 'yes':
        reason = f"[💧 NƯỚC] {reason}"

    data = {
        "parent": {"database_id": EXPENSES_DB_ID},
        "properties": {
            "Reason": {"title": [{"text": {"content": reason}}]},
            "Date": {"date": {"start": date}},
            "Amount": {"number": int(amount)}
        }
    }

    res = requests.post(url, headers=headers, json=data)

    if res.status_code == 200:
        # TRẢ VỀ JSON THÀNH CÔNG THAY VÌ HTML
        return jsonify({"success": True})
    else:
        # TRẢ VỀ LỖI NẾU CÓ
        return jsonify({"success": False, "error": res.text}), 400

    
# 8. API XÓA GIAO DỊCH (MỚI THÊM)
@app.route('/delete-transaction/<page_id>', methods=['POST'])
def delete_transaction(page_id):
    delete_url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {"archived": True} # Lệnh đẩy vào thùng rác
    
    res = requests.patch(delete_url, headers=headers, json=payload)
    
    if res.status_code == 200:
        return jsonify({"success": True})
    else:
        try:
            error_data = res.json()
            if error_data.get("code") == "validation_error" and "archived" in error_data.get("message", ""):
                return jsonify({"success": True})
        except:
            pass
            
        return jsonify({"success": False, "error": res.text}), 400
if __name__ == '__main__':
    app.run(debug=True, port=5000)