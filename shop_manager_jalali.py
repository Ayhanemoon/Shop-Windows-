import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, date


DB_NAME = "shop.db"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def gregorian_to_jalali(gy, gm, gd):
    """Convert Gregorian date to Jalali date (integer year, month, day)."""
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]

    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1
    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    for i in range(gm2):
        g_day_no += g_days_in_month[i]
    if gm2 > 1 and (
        gy % 4 == 0 and gy % 100 != 0 or gy % 400 == 0
    ):
        g_day_no += 1
    g_day_no += gd2

    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    for i, days in enumerate(j_days_in_month):
        if j_day_no < days:
            jm = i + 1
            jd = j_day_no + 1
            break
        j_day_no -= days
    return jy, jm, jd


def jalali_to_gregorian(jy, jm, jd):
    """Convert a Jalali date to Gregorian date."""
    if not 1 <= jm <= 12:
        raise ValueError("ماه شمسی باید بین ۱ تا ۱۲ باشد.")
    if not 1 <= jd <= (31 if jm <= 6 else 30 if jm <= 11 else 30):
        raise ValueError("روز شمسی معتبر نیست.")

    jy += 1595
    days = -355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33 + 3) // 4)
    days += jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += (jm - 7) * 30 + 186

    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        gy += 100 * ((days - 1) // 36524)
        days = (days - 1) % 36524
    if days >= 365:
        gy += 4 * (days // 1461)
        days %= 1461
        if days > 365:
            gy += (days - 1) // 365
            days = (days - 1) % 365

    gd = days + 1
    leap = (
        gy % 4 == 0 and gy % 100 != 0
    ) or gy % 400 == 0
    month_days = [31, 29 if leap else 28, 31, 30, 31, 30,
                  31, 31, 30, 31, 30, 31]
    gm = 1
    for mdays in month_days:
        if gd <= mdays:
            break
        gd -= mdays
        gm += 1
    return gy, gm, gd


def current_jalali_date():
    today = date.today()
    jy, jm, jd = gregorian_to_jalali(today.year, today.month, today.day)
    return f"{jy:04d}-{jm:02d}-{jd:02d}"


def jalali_date_to_gregorian_text(value, end_of_day=False):
    """Parse YYYY-MM-DD Jalali input and return Gregorian SQL timestamp."""
    try:
        parts = [int(part) for part in value.strip().split("-")]
        if len(parts) != 3:
            raise ValueError
        jy, jm, jd = parts
        gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
        # Round-trip check catches impossible dates such as Esfand 31.
        check = gregorian_to_jalali(gy, gm, gd)
        if check != (jy, jm, jd):
            raise ValueError
        parsed = date(gy, gm, gd)
    except (ValueError, TypeError):
        raise ValueError("تاریخ شمسی معتبر نیست؛ قالب صحیح YYYY-MM-DD است.")
    suffix = "23:59:59" if end_of_day else "00:00:00"
    return parsed.strftime("%Y-%m-%d") + " " + suffix


def format_gregorian_timestamp_as_jalali(timestamp):
    try:
        parsed = datetime.strptime(timestamp, DATE_FORMAT)
        jy, jm, jd = gregorian_to_jalali(
            parsed.year, parsed.month, parsed.day
        )
        return f"{jy:04d}/{jm:02d}/{jd:02d} {parsed:%H:%M:%S}"
    except (ValueError, TypeError):
        return timestamp



class Shop:
    """Business logic and SQLite persistence for a small shop."""

    def __init__(self, database=DB_NAME):
        self.connection = sqlite3.connect(database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

    def _create_tables(self):
        with self.connection:
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    purchase_price REAL NOT NULL CHECK(purchase_price >= 0),
                    selling_price REAL NOT NULL CHECK(selling_price >= 0),
                    stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0)
                )
            """)
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    product_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    unit_price REAL NOT NULL CHECK(unit_price >= 0),
                    unit_cost REAL NOT NULL CHECK(unit_cost >= 0),
                    sold_at TEXT NOT NULL,
                    FOREIGN KEY(product_id) REFERENCES products(id)
                        ON DELETE RESTRICT
                )
            """)

    @staticmethod
    def _validate_product(name, purchase_price, selling_price, stock):
        name = name.strip()
        if not name:
            raise ValueError("نام کالا را وارد کنید.")
        try:
            purchase_price = float(purchase_price)
            selling_price = float(selling_price)
            stock = int(stock)
        except (TypeError, ValueError):
            raise ValueError("قیمت‌ها باید عدد و موجودی باید عدد صحیح باشد.")
        if purchase_price < 0 or selling_price < 0:
            raise ValueError("قیمت‌ها نمی‌توانند منفی باشند.")
        if stock < 0:
            raise ValueError("موجودی نمی‌تواند منفی باشد.")
        return name, purchase_price, selling_price, stock

    def add_product(self, name, purchase_price, selling_price, stock):
        values = self._validate_product(
            name, purchase_price, selling_price, stock
        )
        try:
            with self.connection:
                self.connection.execute("""
                    INSERT INTO products
                    (name, purchase_price, selling_price, stock)
                    VALUES (?, ?, ?, ?)
                """, values)
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc):
                raise ValueError("کالایی با این نام از قبل ثبت شده است.")
            raise ValueError("اطلاعات کالا معتبر نیست.") from exc

    def update_product(self, product_id, name, purchase_price,
                       selling_price, stock):
        values = self._validate_product(
            name, purchase_price, selling_price, stock
        )
        try:
            with self.connection:
                cursor = self.connection.execute("""
                    UPDATE products
                    SET name=?, purchase_price=?, selling_price=?, stock=?
                    WHERE id=?
                """, (*values, product_id))
                if cursor.rowcount == 0:
                    raise ValueError("کالای انتخاب‌شده پیدا نشد.")
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc):
                raise ValueError("کالای دیگری با این نام ثبت شده است.")
            raise ValueError("اطلاعات کالا معتبر نیست.") from exc

    def delete_product(self, product_id):
        try:
            with self.connection:
                cursor = self.connection.execute(
                    "DELETE FROM products WHERE id=?", (product_id,)
                )
                if cursor.rowcount == 0:
                    raise ValueError("کالای انتخاب‌شده پیدا نشد.")
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "این کالا سابقه فروش دارد و برای حفظ گزارش‌ها قابل حذف نیست."
            ) from exc

    def add_stock(self, product_id, quantity):
        quantity = int(quantity)
        if quantity <= 0:
            raise ValueError("تعداد ورودی باید بیشتر از صفر باشد.")
        with self.connection:
            cursor = self.connection.execute("""
                UPDATE products SET stock = stock + ? WHERE id = ?
            """, (quantity, product_id))
            if cursor.rowcount == 0:
                raise ValueError("کالای انتخاب‌شده پیدا نشد.")

    def sell_product(self, product_id, quantity):
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            raise ValueError("تعداد فروش باید عدد صحیح باشد.")
        if quantity <= 0:
            raise ValueError("تعداد فروش باید بیشتر از صفر باشد.")

        try:
            with self.connection:
                product = self.connection.execute(
                    "SELECT * FROM products WHERE id=?", (product_id,)
                ).fetchone()
                if product is None:
                    raise ValueError("کالای انتخاب‌شده پیدا نشد.")
                if product["stock"] < quantity:
                    raise ValueError(
                        f"موجودی کافی نیست. موجودی فعلی: {product['stock']}"
                    )

                # Conditional update prevents selling more than available stock.
                cursor = self.connection.execute("""
                    UPDATE products SET stock = stock - ?
                    WHERE id = ? AND stock >= ?
                """, (quantity, product_id, quantity))
                if cursor.rowcount != 1:
                    raise ValueError("موجودی تغییر کرده است؛ دوباره تلاش کنید.")

                self.connection.execute("""
                    INSERT INTO sales
                    (product_id, product_name, quantity, unit_price,
                     unit_cost, sold_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    product_id, product["name"], quantity,
                    product["selling_price"], product["purchase_price"],
                    datetime.now().strftime(DATE_FORMAT)
                ))
        except sqlite3.Error as exc:
            raise RuntimeError(f"خطای پایگاه داده: {exc}") from exc

    def search_products(self, name=""):
        return self.connection.execute("""
            SELECT * FROM products
            WHERE name LIKE ?
            ORDER BY name COLLATE NOCASE
        """, (f"%{name.strip()}%",)).fetchall()

    def get_product(self, product_id):
        return self.connection.execute(
            "SELECT * FROM products WHERE id=?", (product_id,)
        ).fetchone()

    def sales_report(self, start_date, end_date):
        """Dates must be YYYY-MM-DD; end date includes the full day."""
        start_text = jalali_date_to_gregorian_text(start_date)
        end_text = jalali_date_to_gregorian_text(end_date, end_of_day=True)
        if start_text > end_text:
            raise ValueError("تاریخ شروع نباید بعد از تاریخ پایان باشد.")
        return self.connection.execute("""
            SELECT
                COALESCE(SUM(quantity), 0) AS total_quantity,
                COALESCE(SUM(quantity * unit_price), 0) AS total_revenue,
                COALESCE(SUM(quantity * (unit_price - unit_cost)), 0)
                    AS gross_profit,
                COUNT(*) AS transaction_count
            FROM sales
            WHERE sold_at BETWEEN ? AND ?
        """, (start_text, end_text)).fetchone()

    def close(self):
        self.connection.close()


class ShopApp:
    def __init__(self, root):
        self.root = root
        self.shop = Shop()
        self.root.title("سیستم مدیریت فروشگاه")
        self.root.geometry("1100x700")
        self.root.minsize(900, 600)
        self.selected_id = None

        self._configure_style()
        self._build_ui()
        self.refresh_products()

        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _configure_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", padding=6, font=("Tahoma", 10))
        style.configure("TLabel", font=("Tahoma", 10))
        style.configure("Treeview", rowheight=28, font=("Tahoma", 10))
        style.configure("Treeview.Heading", font=("Tahoma", 10, "bold"))
        style.configure("Header.TLabel", font=("Tahoma", 16, "bold"))

    def _build_ui(self):
        header = ttk.Frame(self.root, padding=(12, 10))
        header.pack(fill="x")
        ttk.Label(
            header, text="سیستم مدیریت فروشگاه",
            style="Header.TLabel"
        ).pack(side="right")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.products_tab = ttk.Frame(self.notebook, padding=10)
        self.sales_tab = ttk.Frame(self.notebook, padding=10)
        self.report_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.products_tab, text="مدیریت کالاها")
        self.notebook.add(self.sales_tab, text="ثبت فروش")
        self.notebook.add(self.report_tab, text="گزارش فروش")

        self._build_products_tab()
        self._build_sales_tab()
        self._build_report_tab()

    def _build_products_tab(self):
        form = ttk.LabelFrame(
            self.products_tab, text="اطلاعات کالا", padding=10
        )
        form.pack(fill="x", pady=(0, 10))

        self.name_var = tk.StringVar()
        self.purchase_var = tk.StringVar()
        self.price_var = tk.StringVar()
        self.stock_var = tk.StringVar(value="0")
        fields = [
            ("نام کالا", self.name_var),
            ("قیمت خرید", self.purchase_var),
            ("قیمت فروش", self.price_var),
            ("موجودی", self.stock_var),
        ]
        for col, (label, variable) in enumerate(fields):
            ttk.Label(form, text=label).grid(
                row=0, column=col, padx=5, pady=4, sticky="e"
            )
            ttk.Entry(
                form, textvariable=variable, justify="right", width=20
            ).grid(row=1, column=col, padx=5, pady=4, sticky="ew")
            form.columnconfigure(col, weight=1)

        buttons = ttk.Frame(form)
        buttons.grid(row=2, column=0, columnspan=4, pady=(8, 0))
        ttk.Button(
            buttons, text="افزودن کالا", command=self.add_product
        ).pack(side="right", padx=3)
        ttk.Button(
            buttons, text="ذخیره ویرایش", command=self.update_product
        ).pack(side="right", padx=3)
        ttk.Button(
            buttons, text="حذف کالا", command=self.delete_product
        ).pack(side="right", padx=3)
        ttk.Button(
            buttons, text="پاک کردن فرم", command=self.clear_form
        ).pack(side="right", padx=3)

        search_frame = ttk.Frame(self.products_tab)
        search_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(search_frame, text="جستجو:").pack(side="right", padx=5)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(
            search_frame, textvariable=self.search_var,
            justify="right", width=30
        )
        search_entry.pack(side="right", padx=5)
        search_entry.bind("<KeyRelease>", lambda _event: self.refresh_products())
        ttk.Button(
            search_frame, text="نمایش همه",
            command=self.show_all_products
        ).pack(side="right", padx=5)

        columns = ("id", "name", "purchase", "price", "stock")
        self.products_tree = ttk.Treeview(
            self.products_tab, columns=columns, show="headings",
            selectmode="browse"
        )
        headings = {
            "id": "شناسه", "name": "نام کالا",
            "purchase": "قیمت خرید", "price": "قیمت فروش",
            "stock": "موجودی"
        }
        widths = {"id": 70, "name": 300, "purchase": 160,
                  "price": 160, "stock": 100}
        for col in columns:
            self.products_tree.heading(col, text=headings[col])
            self.products_tree.column(
                col, width=widths[col], anchor="center"
            )
        self.products_tree.pack(fill="both", expand=True)
        self.products_tree.bind("<<TreeviewSelect>>", self.on_product_select)

    def _build_sales_tab(self):
        frame = ttk.LabelFrame(
            self.sales_tab, text="ثبت فروش کالا", padding=16
        )
        frame.pack(fill="x", anchor="n")

        self.sale_product_var = tk.StringVar()
        self.sale_quantity_var = tk.StringVar(value="1")
        ttk.Label(frame, text="کالا:").grid(
            row=0, column=0, padx=6, pady=8, sticky="e"
        )
        self.sale_combo = ttk.Combobox(
            frame, textvariable=self.sale_product_var,
            state="readonly", width=45, justify="right"
        )
        self.sale_combo.grid(row=0, column=1, padx=6, pady=8, sticky="ew")
        ttk.Label(frame, text="تعداد فروش:").grid(
            row=1, column=0, padx=6, pady=8, sticky="e"
        )
        ttk.Entry(
            frame, textvariable=self.sale_quantity_var,
            justify="right", width=20
        ).grid(row=1, column=1, padx=6, pady=8, sticky="w")
        ttk.Button(
            frame, text="ثبت فروش", command=self.sell_product
        ).grid(row=2, column=0, columnspan=2, pady=10)
        frame.columnconfigure(1, weight=1)

        ttk.Label(
            self.sales_tab,
            text="با ثبت فروش، موجودی کالا کم می‌شود و سابقه فروش برای گزارش‌ها ذخیره می‌شود."
        ).pack(anchor="e", pady=12)

    def _build_report_tab(self):
        frame = ttk.LabelFrame(
            self.report_tab, text="بازه گزارش شمسی (YYYY-MM-DD)", padding=12
        )
        frame.pack(fill="x", anchor="n")

        today = current_jalali_date()
        self.start_var = tk.StringVar(value=today[:8] + "01")
        self.end_var = tk.StringVar(value=today)

        ttk.Label(frame, text="از تاریخ شمسی:").grid(
            row=0, column=0, padx=5, pady=6
        )
        ttk.Entry(
            frame, textvariable=self.start_var, width=18, justify="center"
        ).grid(row=0, column=1, padx=5, pady=6)
        ttk.Label(frame, text="تا تاریخ شمسی:").grid(
            row=0, column=2, padx=5, pady=6
        )
        ttk.Entry(
            frame, textvariable=self.end_var, width=18, justify="center"
        ).grid(row=0, column=3, padx=5, pady=6)
        ttk.Button(
            frame, text="تهیه گزارش", command=self.generate_report
        ).grid(row=0, column=4, padx=8, pady=6)

        self.report_text = tk.Text(
            self.report_tab, height=12, font=("Tahoma", 12),
            wrap="word", state="disabled"
        )
        self.report_text.pack(fill="both", expand=True, pady=12)

    def _show_error(self, error):
        messagebox.showerror("خطا", str(error), parent=self.root)

    def _show_info(self, message):
        messagebox.showinfo("پیام", message, parent=self.root)

    def _read_form(self):
        return (
            self.name_var.get(),
            self.purchase_var.get(),
            self.price_var.get(),
            self.stock_var.get()
        )

    def add_product(self):
        try:
            self.shop.add_product(*self._read_form())
            self.refresh_products()
            self.clear_form()
            self._show_info("کالا با موفقیت ثبت شد.")
        except (ValueError, RuntimeError, sqlite3.Error) as exc:
            self._show_error(exc)

    def update_product(self):
        if self.selected_id is None:
            self._show_error("ابتدا یک کالا را از جدول انتخاب کنید.")
            return
        try:
            self.shop.update_product(
                self.selected_id, *self._read_form()
            )
            self.refresh_products()
            self.clear_form()
            self._show_info("اطلاعات کالا به‌روزرسانی شد.")
        except (ValueError, RuntimeError, sqlite3.Error) as exc:
            self._show_error(exc)

    def delete_product(self):
        if self.selected_id is None:
            self._show_error("ابتدا یک کالا را از جدول انتخاب کنید.")
            return
        if not messagebox.askyesno(
            "تأیید حذف", "آیا از حذف این کالا مطمئن هستید؟",
            parent=self.root
        ):
            return
        try:
            self.shop.delete_product(self.selected_id)
            self.refresh_products()
            self.clear_form()
            self._show_info("کالا حذف شد.")
        except (ValueError, RuntimeError, sqlite3.Error) as exc:
            self._show_error(exc)

    def on_product_select(self, _event=None):
        selected = self.products_tree.selection()
        if not selected:
            return
        values = self.products_tree.item(selected[0], "values")
        self.selected_id = int(values[0])
        product = self.shop.get_product(self.selected_id)
        if product:
            self.name_var.set(product["name"])
            self.purchase_var.set(str(product["purchase_price"]))
            self.price_var.set(str(product["selling_price"]))
            self.stock_var.set(str(product["stock"]))

    def clear_form(self):
        self.selected_id = None
        self.name_var.set("")
        self.purchase_var.set("")
        self.price_var.set("")
        self.stock_var.set("0")
        for item in self.products_tree.selection():
            self.products_tree.selection_remove(item)

    def refresh_products(self):
        if not hasattr(self, "products_tree"):
            return
        for item in self.products_tree.get_children():
            self.products_tree.delete(item)
        try:
            products = self.shop.search_products(
                self.search_var.get() if hasattr(self, "search_var") else ""
            )
            for product in products:
                self.products_tree.insert("", "end", values=(
                    product["id"], product["name"],
                    f'{product["purchase_price"]:,.2f}',
                    f'{product["selling_price"]:,.2f}',
                    product["stock"]
                ))
            if hasattr(self, "sale_combo"):
                self.sale_combo["values"] = [
                    f'{p["id"]} - {p["name"]} (موجودی: {p["stock"]})'
                    for p in self.shop.search_products()
                ]
        except sqlite3.Error as exc:
            self._show_error(exc)

    def show_all_products(self):
        self.search_var.set("")
        self.refresh_products()

    def sell_product(self):
        selection = self.sale_combo.current()
        if selection < 0:
            self._show_error("یک کالا را انتخاب کنید.")
            return
        try:
            product_id = int(self.sale_combo["values"][selection].split(" - ", 1)[0])
            self.shop.sell_product(product_id, self.sale_quantity_var.get())
            self.refresh_products()
            self.sale_quantity_var.set("1")
            self._show_info("فروش با موفقیت ثبت شد.")
        except (ValueError, RuntimeError, sqlite3.Error) as exc:
            self._show_error(exc)

    def generate_report(self):
        try:
            report = self.shop.sales_report(
                self.start_var.get().strip(), self.end_var.get().strip()
            )
            content = (
                f"بازه گزارش شمسی: {self.start_var.get()} تا {self.end_var.get()}\n\n"
                f"تعداد کل اقلام فروخته‌شده: {report['total_quantity']:,}\n"
                f"تعداد تراکنش‌های فروش: {report['transaction_count']:,}\n"
                f"درآمد کل فروش: {report['total_revenue']:,.2f}\n"
                f"سود ناخالص: {report['gross_profit']:,.2f}\n\n"
                "سود ناخالص = مجموع (قیمت فروش زمان معامله − قیمت خرید زمان معامله) × تعداد"
            )
            self.report_text.configure(state="normal")
            self.report_text.delete("1.0", "end")
            self.report_text.insert("1.0", content)
            self.report_text.configure(state="disabled")
        except (ValueError, RuntimeError, sqlite3.Error) as exc:
            self._show_error(exc)

    def close(self):
        self.shop.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    ShopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
