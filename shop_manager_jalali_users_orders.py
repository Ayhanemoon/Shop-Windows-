import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, date
import jdatetime

DB_NAME = "shop.db"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def gregorian_to_jalali(gy, gm, gd):
    """Convert Gregorian date to Jalali date."""
    jalali = jdatetime.date.fromgregorian(
        date=date(gy, gm, gd)
    )
    return jalali.year, jalali.month, jalali.day


def jalali_to_gregorian(jy, jm, jd):
    """Convert Jalali date to Gregorian date."""
    return jdatetime.date(
        jy, jm, jd
    ).togregorian().timetuple()[:3]


def current_jalali_date():
    """Return today's Jalali date as YYYY-MM-DD."""
    return jdatetime.date.today().strftime("%Y-%m-%d")


def jalali_date_to_gregorian_text(value, end_of_day=False):
    """Convert Jalali input to Gregorian SQL timestamp."""
    try:
        parts = [int(part) for part in value.strip().split("-")]

        if len(parts) != 3:
            raise ValueError

        jy, jm, jd = parts

        parsed = jdatetime.date(
            jy, jm, jd
        ).togregorian()

    except (ValueError, TypeError, AttributeError):
        raise ValueError(
            "تاریخ شمسی معتبر نیست؛ قالب صحیح YYYY-MM-DD است."
        )

    suffix = "23:59:59" if end_of_day else "00:00:00"

    return parsed.strftime("%Y-%m-%d") + " " + suffix


def format_gregorian_timestamp_as_jalali(timestamp):
    """Convert Gregorian SQL timestamp to Jalali display format."""
    try:
        parsed = datetime.strptime(timestamp, DATE_FORMAT)

        jalali = jdatetime.date.fromgregorian(
            date=parsed.date()
        )

        return (
            f"{jalali.year:04d}/"
            f"{jalali.month:02d}/"
            f"{jalali.day:02d} "
            f"{parsed:%H:%M:%S}"
        )

    except (ValueError, TypeError):
        return timestamp

class Shop:
    """Business logic and SQLite persistence for a small shop."""

    def __init__(self, database=DB_NAME):
        self.connection = sqlite3.connect(database, timeout=15, isolation_level="DEFERRED")
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
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin','operator','customer')),
                    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
                    created_at TEXT NOT NULL
                )
            """)
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    order_date TEXT NOT NULL,
                    total_amount REAL NOT NULL DEFAULT 0 CHECK(total_amount >= 0),
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending','confirmed','processing','completed','cancelled')),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE RESTRICT
                )
            """)
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    product_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    unit_price REAL NOT NULL CHECK(unit_price >= 0),
                    unit_cost REAL NOT NULL CHECK(unit_cost >= 0),
                    FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE RESTRICT
                )
            """)
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date)")

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
            WITH all_sales AS (
                SELECT quantity, unit_price, unit_cost, sold_at AS sale_date
                FROM sales WHERE sold_at BETWEEN ? AND ?
                UNION ALL
                SELECT oi.quantity, oi.unit_price, oi.unit_cost, o.order_date AS sale_date
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                WHERE o.status = 'completed' AND o.order_date BETWEEN ? AND ?
            )
            SELECT
                COALESCE(SUM(quantity), 0) AS total_quantity,
                COALESCE(SUM(quantity * unit_price), 0) AS total_revenue,
                COALESCE(SUM(quantity * (unit_price - unit_cost)), 0) AS gross_profit,
                COUNT(*) AS transaction_count
            FROM all_sales
        """, (start_text, end_text, start_text, end_text)).fetchone()

    # ---- User accounts and role-based access ----
    @staticmethod
    def hash_password(password, salt=None):
        import os, hashlib, base64
        if len(password) < 8:
            raise ValueError("رمز عبور باید حداقل ۸ نویسه باشد.")
        salt = salt or os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()

    @staticmethod
    def verify_password(password, stored):
        import hashlib, base64, hmac
        try:
            salt_text, digest_text = stored.split("$", 1)
            salt = base64.b64decode(salt_text)
            expected = base64.b64decode(digest_text)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    def ensure_default_admin(self):
        row = self.connection.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
        if row is None:
            self.create_user("مدیر سیستم", "admin", "Admin1234", "admin")

    def create_user(self, full_name, username, password, role):
        full_name, username = full_name.strip(), username.strip()
        if not full_name or not username:
            raise ValueError("نام و نام کاربری الزامی است.")
        if role not in ("admin", "operator", "customer"):
            raise ValueError("نوع کاربر نامعتبر است.")
        password_hash = self.hash_password(password)
        try:
            with self.connection:
                cur = self.connection.execute(
                    "INSERT INTO users(full_name,username,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                    (full_name, username, password_hash, role, datetime.now().strftime(DATE_FORMAT)))
                return cur.lastrowid
        except sqlite3.IntegrityError as exc:
            raise ValueError("این نام کاربری قبلاً ثبت شده است.") from exc

    def authenticate(self, username, password):
        user = self.connection.execute(
            "SELECT * FROM users WHERE username=? AND is_active=1", (username.strip(),)).fetchone()
        if user and self.verify_password(password, user["password_hash"]):
            return user
        return None

    def list_users(self):
        return self.connection.execute(
            "SELECT id,full_name,username,role,is_active FROM users ORDER BY id").fetchall()

    def set_user_active(self, user_id, active):
        with self.connection:
            self.connection.execute("UPDATE users SET is_active=? WHERE id=?", (int(bool(active)), user_id))

    def change_password(self, user_id, new_password):
        password_hash = self.hash_password(new_password)
        with self.connection:
            self.connection.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))

    # ---- Customer orders ----
    def create_order(self, user_id, cart):
        """cart is {product_id: quantity}; stock decrement and order insert are atomic."""
        if not cart:
            raise ValueError("سبد خرید خالی است.")
        normalized = {}
        for product_id, quantity in cart.items():
            try:
                product_id, quantity = int(product_id), int(quantity)
            except (TypeError, ValueError):
                raise ValueError("شناسه کالا یا تعداد نامعتبر است.")
            if quantity <= 0:
                raise ValueError("تعداد هر کالا باید بیشتر از صفر باشد.")
            normalized[product_id] = normalized.get(product_id, 0) + quantity
        try:
            # BEGIN IMMEDIATE obtains SQLite's write reservation before stock reads.
            self.connection.execute("BEGIN IMMEDIATE")
            user = self.connection.execute("SELECT id,role,is_active FROM users WHERE id=?", (user_id,)).fetchone()
            if user is None or not user["is_active"]:
                raise ValueError("حساب کاربری فعال نیست.")
            order_date = datetime.now().strftime(DATE_FORMAT)
            cur = self.connection.execute(
                "INSERT INTO orders(user_id,order_date,total_amount,status) VALUES(?,?,0,'pending')",
                (user_id, order_date))
            order_id = cur.lastrowid
            total = 0
            for product_id, quantity in normalized.items():
                product = self.connection.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
                if product is None:
                    raise ValueError("یکی از کالاهای سبد خرید دیگر وجود ندارد.")
                update = self.connection.execute(
                    "UPDATE products SET stock=stock-? WHERE id=? AND stock>=?",
                    (quantity, product_id, quantity))
                if update.rowcount != 1:
                    raise ValueError(f"موجودی کالای «{product['name']}» برای این سفارش کافی نیست.")
                total += quantity * product["selling_price"]
                self.connection.execute(
                    "INSERT INTO order_items(order_id,product_id,product_name,quantity,unit_price,unit_cost) VALUES(?,?,?,?,?,?)",
                    (order_id, product_id, product["name"], quantity, product["selling_price"], product["purchase_price"]))
            self.connection.execute("UPDATE orders SET total_amount=? WHERE id=?", (total, order_id))
            self.connection.commit()
            return order_id
        except Exception:
            self.connection.rollback()
            raise

    def list_orders(self, user_id=None):
        sql = """SELECT o.*,u.full_name,u.username FROM orders o JOIN users u ON u.id=o.user_id"""
        params = ()
        if user_id is not None:
            sql += " WHERE o.user_id=?"
            params = (user_id,)
        return self.connection.execute(sql + " ORDER BY o.id DESC", params).fetchall()

    def order_items(self, order_id):
        return self.connection.execute(
            "SELECT * FROM order_items WHERE order_id=? ORDER BY id", (order_id,)).fetchall()

    def update_order_status(self, order_id, new_status):
        allowed = {"confirmed", "processing", "completed", "cancelled"}
        if new_status not in allowed:
            raise ValueError("وضعیت سفارش نامعتبر است.")
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            order = self.connection.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if order is None:
                raise ValueError("سفارش پیدا نشد.")
            old = order["status"]
            transitions = {"pending": {"confirmed", "cancelled"},
                           "confirmed": {"processing", "cancelled"},
                           "processing": {"completed", "cancelled"},
                           "completed": set(), "cancelled": set()}
            if new_status not in transitions[old]:
                raise ValueError("تغییر وضعیت از حالت فعلی مجاز نیست.")
            if new_status == "cancelled":
                for item in self.order_items(order_id):
                    self.connection.execute("UPDATE products SET stock=stock+? WHERE id=?",
                                            (item["quantity"], item["product_id"]))
            self.connection.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def close(self):
        self.connection.close()


class LoginApp:
    def __init__(self, root):
        self.root = root
        self.shop = Shop()
        self.shop.ensure_default_admin()
        self.root.title("ورود به سیستم مدیریت فروشگاه")
        self.root.geometry("430x300")
        self.root.resizable(False, False)
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self):
        frame = ttk.Frame(self.root, padding=25)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="ورود به فروشگاه", font=("Tahoma", 16, "bold")).pack(pady=(5, 18))
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        ttk.Label(frame, text="نام کاربری").pack(anchor="e")
        ttk.Entry(frame, textvariable=self.username, justify="right").pack(fill="x", pady=(3, 10))
        ttk.Label(frame, text="رمز عبور").pack(anchor="e")
        entry = ttk.Entry(frame, textvariable=self.password, show="*", justify="right")
        entry.pack(fill="x", pady=(3, 15))
        entry.bind("<Return>", lambda _e: self.login())
        ttk.Button(frame, text="ورود", command=self.login).pack(fill="x")
        ttk.Label(frame, text="ورود اولیه مدیر: admin / Admin1234  |  پس از ورود رمز را تغییر دهید.",
                  foreground="#9a5b00", wraplength=360).pack(pady=12)

    def login(self):
        user = self.shop.authenticate(self.username.get(), self.password.get())
        if not user:
            messagebox.showerror("ورود ناموفق", "نام کاربری یا رمز عبور اشتباه است یا حساب غیرفعال شده.", parent=self.root)
            return
        self.root.withdraw()
        DashboardApp(self.root, self.shop, user, self.logout)

    def logout(self):
        self.password.set("")
        self.username.set("")
        self.root.deiconify()

    def close(self):
        self.shop.close()
        self.root.destroy()


class DashboardApp:
    ROLE_NAMES = {"admin": "مدیر", "operator": "اپراتور", "customer": "مشتری"}
    STATUS_NAMES = {"pending": "در انتظار بررسی", "confirmed": "تأیید شده",
                    "processing": "در حال آماده‌سازی", "completed": "تکمیل شده",
                    "cancelled": "لغو شده"}

    def __init__(self, login_root, shop, user, on_logout):
        self.login_root, self.shop, self.user, self.on_logout = login_root, shop, user, on_logout
        self.window = tk.Toplevel(login_root)
        self.window.title("سیستم مدیریت فروشگاه")
        self.window.geometry("1120x720")
        self.window.minsize(900, 600)
        self.cart = {}
        self.selected_product_id = None
        self.selected_order_id = None
        self._configure_style()
        self._build()
        self.refresh_all()
        self.window.protocol("WM_DELETE_WINDOW", self.logout)

    def _configure_style(self):
        style = ttk.Style()
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("TButton", padding=6, font=("Tahoma", 9))
        style.configure("TLabel", font=("Tahoma", 9))
        style.configure("Treeview", rowheight=27, font=("Tahoma", 9))
        style.configure("Treeview.Heading", font=("Tahoma", 9, "bold"))

    def _build(self):
        header = ttk.Frame(self.window, padding=10); header.pack(fill="x")
        ttk.Label(header, text=f"کاربر: {self.user['full_name']}  |  نقش: {self.ROLE_NAMES[self.user['role']]}",
                  font=("Tahoma", 11, "bold")).pack(side="right")
        ttk.Button(header, text="تغییر رمز عبور", command=self.change_password).pack(side="left", padx=4)
        ttk.Button(header, text="خروج از حساب", command=self.logout).pack(side="left", padx=4)
        self.tabs = ttk.Notebook(self.window); self.tabs.pack(fill="both", expand=True, padx=10, pady=(0,10))
        role = self.user["role"]
        if role in ("admin", "operator"):
            self._build_inventory_tab()
        if role == "customer":
            self._build_catalog_tab()
        self._build_orders_tab()
        if role in ("admin", "operator"):
            self._build_report_tab()
        if role == "admin":
            self._build_users_tab()

    def _build_inventory_tab(self):
        tab = ttk.Frame(self.tabs, padding=10); self.tabs.add(tab, text="مدیریت کالاها")
        form = ttk.LabelFrame(tab, text="اطلاعات کالا", padding=8); form.pack(fill="x")
        self.p_name, self.p_cost, self.p_price, self.p_stock = (tk.StringVar() for _ in range(4))
        for i,(label,var) in enumerate((("نام کالا",self.p_name),("قیمت خرید",self.p_cost),("قیمت فروش",self.p_price),("موجودی",self.p_stock))):
            ttk.Label(form,text=label).grid(row=0,column=i,padx=4); ttk.Entry(form,textvariable=var,justify="right",width=18).grid(row=1,column=i,padx=4,pady=4)
        buttons=ttk.Frame(form); buttons.grid(row=2,column=0,columnspan=4,pady=5)
        ttk.Button(buttons,text="افزودن",command=self.add_product).pack(side="right",padx=3)
        ttk.Button(buttons,text="ویرایش",command=self.edit_product).pack(side="right",padx=3)
        ttk.Button(buttons,text="حذف",command=self.delete_product).pack(side="right",padx=3)
        ttk.Button(buttons,text="پاک کردن",command=self.clear_product_form).pack(side="right",padx=3)
        self.product_tree=self._tree(tab,("id","name","cost","price","stock"),("شناسه","کالا","قیمت خرید","قیمت فروش","موجودی"))
        self.product_tree.bind("<<TreeviewSelect>>",self.select_product)

    def _build_catalog_tab(self):
        tab=ttk.Frame(self.tabs,padding=10); self.tabs.add(tab,text="فروشگاه و سبد خرید")
        ttk.Label(tab,text="کالاهای قابل سفارش").pack(anchor="e")
        self.catalog_tree=self._tree(tab,("id","name","price","stock"),("شناسه","کالا","قیمت","موجودی"), height=7)
        row=ttk.Frame(tab); row.pack(fill="x",pady=6)
        self.cart_qty=tk.StringVar(value="1")
        ttk.Label(row,text="تعداد:").pack(side="right"); ttk.Entry(row,textvariable=self.cart_qty,width=8).pack(side="right",padx=5)
        ttk.Button(row,text="افزودن به سبد",command=self.add_to_cart).pack(side="right",padx=5)
        self.cart_tree=self._tree(tab,("id","name","qty","unit","total"),("شناسه","کالا","تعداد","قیمت واحد","جمع"), height=6)
        bottom=ttk.Frame(tab); bottom.pack(fill="x",pady=6)
        self.cart_total_label=ttk.Label(bottom,text="جمع سبد: ۰",font=("Tahoma",11,"bold")); self.cart_total_label.pack(side="right")
        ttk.Button(bottom,text="حذف کالای انتخابی از سبد",command=self.remove_from_cart).pack(side="left",padx=4)
        ttk.Button(bottom,text="ثبت نهایی سفارش",command=self.place_order).pack(side="left",padx=4)

    def _build_orders_tab(self):
        tab=ttk.Frame(self.tabs,padding=10); self.tabs.add(tab,text="سفارش‌ها")
        self.orders_tree=self._tree(tab,("id","customer","date","total","status"),("شماره","مشتری","تاریخ","مبلغ کل","وضعیت"))
        self.orders_tree.bind("<<TreeviewSelect>>",self.select_order)
        self.items_tree=self._tree(tab,("name","qty","price","total"),("کالا","تعداد","قیمت واحد","جمع"),height=6)
        if self.user["role"] in ("admin","operator"):
            row=ttk.Frame(tab); row.pack(fill="x",pady=6)
            ttk.Button(row,text="تأیید سفارش",command=lambda:self.change_order_status("confirmed")).pack(side="right",padx=3)
            ttk.Button(row,text="شروع آماده‌سازی",command=lambda:self.change_order_status("processing")).pack(side="right",padx=3)
            ttk.Button(row,text="تکمیل سفارش",command=lambda:self.change_order_status("completed")).pack(side="right",padx=3)
            ttk.Button(row,text="لغو سفارش و بازگشت موجودی",command=lambda:self.change_order_status("cancelled")).pack(side="right",padx=3)

    def _build_report_tab(self):
        tab=ttk.Frame(self.tabs,padding=12); self.tabs.add(tab,text="گزارش فروش")
        today=current_jalali_date(); self.r_start=tk.StringVar(value=today[:8]+"01"); self.r_end=tk.StringVar(value=today)
        row=ttk.Frame(tab); row.pack(anchor="e")
        ttk.Label(row,text="از تاریخ شمسی").pack(side="right"); ttk.Entry(row,textvariable=self.r_start,width=14).pack(side="right",padx=4)
        ttk.Label(row,text="تا تاریخ شمسی").pack(side="right"); ttk.Entry(row,textvariable=self.r_end,width=14).pack(side="right",padx=4)
        ttk.Button(row,text="گزارش",command=self.generate_report).pack(side="right",padx=4)
        self.report_box=tk.Text(tab,font=("Tahoma",11),height=12,state="disabled"); self.report_box.pack(fill="both",expand=True,pady=10)

    def _build_users_tab(self):
        tab=ttk.Frame(self.tabs,padding=10); self.tabs.add(tab,text="مدیریت کاربران")
        form=ttk.LabelFrame(tab,text="ایجاد حساب",padding=8); form.pack(fill="x")
        self.u_name,self.u_username,self.u_password=tk.StringVar(),tk.StringVar(),tk.StringVar()
        for i,(label,var) in enumerate((("نام و نام خانوادگی",self.u_name),("نام کاربری",self.u_username),("رمز عبور",self.u_password))):
            ttk.Label(form,text=label).grid(row=0,column=i); ttk.Entry(form,textvariable=var,show="*" if i==2 else "",justify="right",width=22).grid(row=1,column=i,padx=4,pady=4)
        self.u_role=tk.StringVar(value="customer")
        ttk.Label(form,text="نقش").grid(row=0,column=3); ttk.Combobox(form,textvariable=self.u_role,values=("customer","operator","admin"),state="readonly",width=14).grid(row=1,column=3,padx=4)
        ttk.Button(form,text="ایجاد کاربر",command=self.create_user).grid(row=1,column=4,padx=8)
        self.users_tree=self._tree(tab,("id","name","username","role","active"),("شناسه","نام","نام کاربری","نقش","فعال"))
        row=ttk.Frame(tab); row.pack(fill="x",pady=5)
        ttk.Button(row,text="فعال/غیرفعال کردن حساب انتخابی",command=self.toggle_user).pack(side="right")

    def _tree(self,parent,columns,headings,height=12):
        tree=ttk.Treeview(parent,columns=columns,show="headings",height=height,selectmode="browse")
        for c,h in zip(columns,headings): tree.heading(c,text=h); tree.column(c,width=150,anchor="center")
        tree.pack(fill="both",expand=True,pady=6); return tree

    def refresh_all(self):
        if hasattr(self,"product_tree"): self.refresh_inventory()
        if hasattr(self,"catalog_tree"): self.refresh_catalog()
        self.refresh_orders()
        if hasattr(self,"users_tree"): self.refresh_users()

    def refresh_inventory(self):
        self._clear_tree(self.product_tree)
        for p in self.shop.search_products(): self.product_tree.insert("","end",values=(p["id"],p["name"],p["purchase_price"],p["selling_price"],p["stock"]))

    def refresh_catalog(self):
        self._clear_tree(self.catalog_tree)
        for p in self.shop.search_products(): self.catalog_tree.insert("","end",values=(p["id"],p["name"],p["selling_price"],p["stock"]))
        self._refresh_cart()

    @staticmethod
    def _clear_tree(tree):
        for item in tree.get_children(): tree.delete(item)

    def refresh_orders(self):
        self._clear_tree(self.orders_tree)
        uid=self.user["id"] if self.user["role"]=="customer" else None
        for o in self.shop.list_orders(uid): self.orders_tree.insert("","end",values=(o["id"],o["full_name"],o["order_date"],f"{o['total_amount']:,.0f}",self.STATUS_NAMES[o["status"]]))

    def refresh_users(self):
        self._clear_tree(self.users_tree)
        roles={"admin":"مدیر","operator":"اپراتور","customer":"مشتری"}
        for u in self.shop.list_users(): self.users_tree.insert("","end",values=(u["id"],u["full_name"],u["username"],roles[u["role"]],"بله" if u["is_active"] else "خیر"))

    def add_product(self):
        try:
            self.shop.add_product(self.p_name.get(),self.p_cost.get(),self.p_price.get(),self.p_stock.get()); self.refresh_all(); self.clear_product_form(); messagebox.showinfo("موفق","کالا ثبت شد.",parent=self.window)
        except Exception as e: self.error(e)

    def select_product(self,_e=None):
        sel=self.product_tree.selection()
        if not sel:return
        vals=self.product_tree.item(sel[0],"values"); self.selected_product_id=int(vals[0]); p=self.shop.get_product(self.selected_product_id)
        self.p_name.set(p["name"]); self.p_cost.set(str(p["purchase_price"])); self.p_price.set(str(p["selling_price"])); self.p_stock.set(str(p["stock"]))

    def edit_product(self):
        if not self.selected_product_id:return self.error("ابتدا کالا را انتخاب کنید.")
        try:self.shop.update_product(self.selected_product_id,self.p_name.get(),self.p_cost.get(),self.p_price.get(),self.p_stock.get()); self.refresh_all(); self.clear_product_form()
        except Exception as e:self.error(e)

    def delete_product(self):
        if not self.selected_product_id:return self.error("ابتدا کالا را انتخاب کنید.")
        if not messagebox.askyesno("تأیید","کالا حذف شود؟",parent=self.window):return
        try:self.shop.delete_product(self.selected_product_id); self.refresh_all(); self.clear_product_form()
        except Exception as e:self.error(e)

    def clear_product_form(self):
        self.selected_product_id=None
        for v in (self.p_name,self.p_cost,self.p_price):v.set("")
        self.p_stock.set("0")

    def add_to_cart(self):
        sel=self.catalog_tree.selection()
        if not sel:return self.error("یک کالا انتخاب کنید.")
        try:
            vals=self.catalog_tree.item(sel[0],"values"); pid=int(vals[0]); qty=int(self.cart_qty.get())
            if qty<=0:raise ValueError("تعداد باید بیشتر از صفر باشد.")
            product=self.shop.get_product(pid)
            if not product:raise ValueError("کالا پیدا نشد.")
            new_qty=self.cart.get(pid,0)+qty
            if new_qty>product["stock"]:raise ValueError("تعداد درخواستی از موجودی فعلی بیشتر است.")
            self.cart[pid]=new_qty; self._refresh_cart()
        except Exception as e:self.error(e)

    def _refresh_cart(self):
        if not hasattr(self,"cart_tree"):return
        self._clear_tree(self.cart_tree); total=0
        for pid,qty in self.cart.items():
            p=self.shop.get_product(pid)
            if p:
                line=qty*p["selling_price"]; total+=line
                self.cart_tree.insert("","end",values=(pid,p["name"],qty,f"{p['selling_price']:,.0f}",f"{line:,.0f}"))
        self.cart_total_label.config(text=f"جمع سبد: {total:,.0f}")

    def remove_from_cart(self):
        sel=self.cart_tree.selection()
        if not sel:return
        pid=int(self.cart_tree.item(sel[0],"values")[0]); self.cart.pop(pid,None); self._refresh_cart()

    def place_order(self):
        if not self.cart:return self.error("سبد خرید خالی است.")
        if not messagebox.askyesno("ثبت سفارش","سفارش نهایی و موجودی رزرو شود؟",parent=self.window):return
        try:
            oid=self.shop.create_order(self.user["id"],self.cart); self.cart.clear(); self.refresh_all()
            messagebox.showinfo("سفارش ثبت شد",f"سفارش شماره {oid} با وضعیت «در انتظار بررسی» ثبت شد.",parent=self.window)
        except Exception as e:self.error(e)

    def select_order(self,_e=None):
        sel=self.orders_tree.selection()
        if not sel:return
        self.selected_order_id=int(self.orders_tree.item(sel[0],"values")[0]); self._clear_tree(self.items_tree)
        for item in self.shop.order_items(self.selected_order_id):self.items_tree.insert("","end",values=(item["product_name"],item["quantity"],f"{item['unit_price']:,.0f}",f"{item['quantity']*item['unit_price']:,.0f}"))

    def change_order_status(self,status):
        if not self.selected_order_id:return self.error("ابتدا سفارش را انتخاب کنید.")
        try:self.shop.update_order_status(self.selected_order_id,status); self.refresh_all(); messagebox.showinfo("موفق","وضعیت سفارش تغییر کرد.",parent=self.window)
        except Exception as e:self.error(e)

    def create_user(self):
        try:self.shop.create_user(self.u_name.get(),self.u_username.get(),self.u_password.get(),self.u_role.get()); self.refresh_users(); self.u_name.set("");self.u_username.set("");self.u_password.set("");messagebox.showinfo("موفق","کاربر ایجاد شد.",parent=self.window)
        except Exception as e:self.error(e)

    def toggle_user(self):
        sel=self.users_tree.selection()
        if not sel:return self.error("یک کاربر انتخاب کنید.")
        vals=self.users_tree.item(sel[0],"values"); uid=int(vals[0])
        if uid==self.user["id"]:return self.error("نمی‌توانید حساب خودتان را غیرفعال کنید.")
        self.shop.set_user_active(uid, vals[4]!="بله"); self.refresh_users()

    def generate_report(self):
        try:
            r=self.shop.sales_report(self.r_start.get(),self.r_end.get())
            text=(f"بازه شمسی: {self.r_start.get()} تا {self.r_end.get()}\n\nتعداد اقلام فروخته‌شده: {r['total_quantity']}\nتعداد ردیف‌های فروش: {r['transaction_count']}\nدرآمد کل: {r['total_revenue']:,.0f}\nسود ناخالص: {r['gross_profit']:,.0f}\n\nگزارش شامل فروش مستقیم و سفارش‌های تکمیل‌شده مشتریان است.")
            self.report_box.config(state="normal");self.report_box.delete("1.0","end");self.report_box.insert("1.0",text);self.report_box.config(state="disabled")
        except Exception as e:self.error(e)

    def change_password(self):
        from tkinter import simpledialog
        pw=simpledialog.askstring("تغییر رمز","رمز عبور جدید (حداقل ۸ نویسه):",show="*",parent=self.window)
        if pw is None:return
        try:self.shop.change_password(self.user["id"],pw);messagebox.showinfo("موفق","رمز عبور تغییر کرد.",parent=self.window)
        except Exception as e:self.error(e)

    def error(self,e):messagebox.showerror("خطا",str(e),parent=self.window)

    def logout(self):
        self.window.destroy();self.on_logout()


def main():
    root=tk.Tk();LoginApp(root);root.mainloop()


if __name__ == "__main__":
    main()
ش