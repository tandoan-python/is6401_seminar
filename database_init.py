"""
Module for initializing the database schema and automatically generating test data.
Separated to ensure the independence of the data preparation process.
"""
import random
from typing import List, Dict, Any
from faker import Faker
from sqlalchemy import create_engine, text
from config import Config

class DatabaseManager:
    """Manages connections and initialization of the Database Schema."""
    
    def __init__(self, db_uri: str):
        self.engine = create_engine(db_uri)
    
    def create_tables(self) -> None:
        """Initializes 16 entity tables according to the MES system's ER Diagram."""
        print("[INFO] Executing database schema initialization process...")
        
        tables_ddl = [
            "CREATE TABLE IF NOT EXISTS customers (id INT AUTO_INCREMENT PRIMARY KEY, customer_name VARCHAR(255), user_id INT);",
            "CREATE TABLE IF NOT EXISTS orders (id INT AUTO_INCREMENT PRIMARY KEY, user_id INT, order_name VARCHAR(255), created_at DATETIME, status VARCHAR(50));",
            "CREATE TABLE IF NOT EXISTS products_types (id INT AUTO_INCREMENT PRIMARY KEY, description VARCHAR(255));",
            "CREATE TABLE IF NOT EXISTS products (id INT AUTO_INCREMENT PRIMARY KEY, products_type_id INT, attributes VARCHAR(255));",
            "CREATE TABLE IF NOT EXISTS materials (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), unit VARCHAR(50), type VARCHAR(50));",
            "CREATE TABLE IF NOT EXISTS warehouse (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255));",
            "CREATE TABLE IF NOT EXISTS working_group (id INT AUTO_INCREMENT PRIMARY KEY, type VARCHAR(50), name VARCHAR(255));",
            "CREATE TABLE IF NOT EXISTS order_product (id INT AUTO_INCREMENT PRIMARY KEY, order_id INT, product_id INT, number INT);",
            "CREATE TABLE IF NOT EXISTS warehouse_material (id INT AUTO_INCREMENT PRIMARY KEY, warehouse_id INT, material_id INT, left_number INT, total_number INT);",
            "CREATE TABLE IF NOT EXISTS warehouse_product (id INT AUTO_INCREMENT PRIMARY KEY, warehouse_id INT, product_id INT, left_number INT);",
            "CREATE TABLE IF NOT EXISTS wip_material (id INT AUTO_INCREMENT PRIMARY KEY, wip_id INT, origin_material_id INT, number INT);",
            "CREATE TABLE IF NOT EXISTS product_material (id INT AUTO_INCREMENT PRIMARY KEY, product_id INT, material_id INT, number INT);",
            "CREATE TABLE IF NOT EXISTS sewing_tasks (id INT AUTO_INCREMENT PRIMARY KEY, start_time DATETIME, end_time DATETIME, working_group_id INT, order_product_id INT, planned_number INT, completed_number INT, status INT);",
            "CREATE TABLE IF NOT EXISTS cutting_tasks (id INT AUTO_INCREMENT PRIMARY KEY, start_time DATETIME, end_time DATETIME, working_group_id INT, order_product_id INT, produced_wip_id INT, planned_number INT, completed_number INT, status INT);",
            "CREATE TABLE IF NOT EXISTS cutting_material_allocation (id INT AUTO_INCREMENT PRIMARY KEY, warehouse_material_id INT, cutting_task_id INT, allocated_num INT, is_allocated INT);",
            "CREATE TABLE IF NOT EXISTS sewing_material_allocation (id INT AUTO_INCREMENT PRIMARY KEY, warehouse_material_id INT, sewing_task_id INT, allocated_num INT, is_allocated INT);"
        ]
        
        with self.engine.connect() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
            for ddl in tables_ddl:
                conn.execute(text(ddl))
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
            conn.commit()
        print("[INFO] Database schema setup is complete.")


class DataGenerator:
    """Module for automatically generating test data based on a Scale Factor."""
    
    def __init__(self, db_manager: DatabaseManager, scale_factor: int):
        self.engine = db_manager.engine
        self.scale = scale_factor
        self.faker = Faker()
        
        # Set entity ratios depending on scale factor
        self.num_orders = self.scale
        self.num_customers = max(5, int(self.scale * 0.1))
        self.num_products = max(10, int(self.scale * 0.2))
        self.num_groups = max(4, int(self.scale * 0.05))
        
        # Categories with relatively fixed sizes
        self.num_materials = 30
        self.num_warehouses = 3
        self.num_product_types = 5

    def _execute_batch(self, query: str, params_list: List[Dict[str, Any]]) -> None:
        """Executes batch insert to optimize performance."""
        if not params_list: return
        with self.engine.connect() as conn:
            conn.execute(text(query), params_list)
            conn.commit()

    def generate_all(self) -> None:
        """Triggers the comprehensive simulated data generation process."""
        print(f"[INFO] Starting test data generation process (Scale Factor: {self.scale})...")
        self._generate_master_data()
        self._generate_transactional_data()
        self._inject_benchmark_data()
        print("[INFO] Test data generation process completed successfully.")

    def _generate_master_data(self) -> None:
        """Generates core master data."""
        customers = [{"c_name": self.faker.company(), "uid": self.faker.random_int(100, 999)} for _ in range(self.num_customers)]
        self._execute_batch("INSERT INTO customers (customer_name, user_id) VALUES (:c_name, :uid)", customers)
        
        p_types = [{"desc": t} for t in ['Shirt', 'Trousers', 'Skirt', 'Jacket', 'Uniform']]
        self._execute_batch("INSERT INTO products_types (description) VALUES (:desc)", p_types)
        
        products = [{"pt_id": random.randint(1, self.num_product_types), "attr": f"{self.faker.color_name()}, Size {random.choice(['S','M','L','XL'])}"} for _ in range(self.num_products)]
        self._execute_batch("INSERT INTO products (products_type_id, attributes) VALUES (:pt_id, :attr)", products)

        materials = [{"name": f"Material {self.faker.word()}", "unit": random.choice(["Meter", "Piece", "Kg"]), "type": random.choice(["Fabric", "Thread", "Button", "Accessory"])} for _ in range(self.num_materials)]
        self._execute_batch("INSERT INTO materials (name, unit, type) VALUES (:name, :unit, :type)", materials)
        
        warehouses = [{"name": f"Warehouse {i+1}"} for i in range(self.num_warehouses)]
        self._execute_batch("INSERT INTO warehouse (name) VALUES (:name)", warehouses)

        groups = [{"type": "Cutting" if i % 2 == 0 else "Sewing", "name": f"Team {self.faker.first_name()}"} for i in range(self.num_groups)]
        self._execute_batch("INSERT INTO working_group (type, name) VALUES (:type, :name)", groups)

    def _generate_transactional_data(self) -> None:
        """Generates dynamic transactional data."""
        orders = [{"uid": random.randint(1, self.num_customers), "o_name": f"Order {self.faker.word().capitalize()}", "cat": self.faker.date_time_this_year(), "status": "Pending"} for _ in range(self.num_orders)]
        self._execute_batch("INSERT INTO orders (user_id, order_name, created_at, status) VALUES (:uid, :o_name, :cat, :status)", orders)

        order_products = []
        for o_id in range(1, self.num_orders + 1):
            for _ in range(random.randint(1, 3)):
                order_products.append({"o_id": o_id, "p_id": random.randint(1, self.num_products), "num": random.randint(50, 500)})
        self._execute_batch("INSERT INTO order_product (order_id, product_id, number) VALUES (:o_id, :p_id, :num)", order_products)

        wh_materials = [{"wh_id": random.randint(1, self.num_warehouses), "mat_id": random.randint(1, self.num_materials), "left_num": random.randint(1000, 5000), "tot_num": random.randint(5000, 10000)} for _ in range(self.num_materials * 2)]
        self._execute_batch("INSERT INTO warehouse_material (warehouse_id, material_id, left_number, total_number) VALUES (:wh_id, :mat_id, :left_num, :tot_num)", wh_materials)

    def _inject_benchmark_data(self) -> None:
        """Injects benchmark data used for Evaluation."""
        queries = [
            "INSERT INTO customers (id, customer_name, user_id) VALUES (9999, 'Hong Kong Polytechnic University', 101) ON DUPLICATE KEY UPDATE id=id;",
            "INSERT INTO orders (id, user_id, order_name, created_at, status) VALUES (9999, 101, 'Emily Dress', '2024-04-05', 'Pending') ON DUPLICATE KEY UPDATE id=id;",
            "INSERT INTO order_product (id, order_id, product_id, number) VALUES (9999, 9999, 1, 150) ON DUPLICATE KEY UPDATE id=id;"
        ]
        with self.engine.connect() as conn:
            for q in queries:
                conn.execute(text(q))
            conn.commit()


if __name__ == "__main__":
    print("=====================================================")
    print("[SYSTEM] STARTING DATABASE INITIALIZATION PROGRAM")
    print("=====================================================")
    db_manager = DatabaseManager(Config.DB_URI)
    db_manager.create_tables()
    
    generator = DataGenerator(db_manager, Config.SCALE_FACTOR)
    generator.generate_all()
    print("[SYSTEM] ALL PROCESSES COMPLETED SUCCESSFULLY.")
