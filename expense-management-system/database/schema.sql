CREATE TABLE employees (
    employee_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    department TEXT,
    designation TEXT
);

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT NOT NULL
);

CREATE TABLE expenses (
    expense_id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER,
    category_id INTEGER,
    amount REAL NOT NULL,
    expense_date DATE NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'Pending',

    FOREIGN KEY(employee_id)
        REFERENCES employees(employee_id),

    FOREIGN KEY(category_id)
        REFERENCES categories(category_id)
);

CREATE TABLE travel_requests (
    travel_id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER,
    destination TEXT NOT NULL,
    purpose TEXT NOT NULL,
    start_date DATE,
    end_date DATE,
    estimated_cost REAL,
    status TEXT DEFAULT 'Pending',

    FOREIGN KEY(employee_id)
        REFERENCES employees(employee_id)
);

CREATE TABLE travel_expenses (
    travel_expense_id INTEGER PRIMARY KEY AUTOINCREMENT,
    travel_id INTEGER,
    expense_type TEXT,
    amount REAL,
    expense_date DATE,
    description TEXT,
    status TEXT DEFAULT 'Pending',

    FOREIGN KEY(travel_id)
        REFERENCES travel_requests(travel_id)
);