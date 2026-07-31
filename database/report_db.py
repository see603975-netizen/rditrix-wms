"""ReportDBMixin：統計報表（出貨彙總、損耗彙總）。"""
from utils.constants import *


class ReportDBMixin:
    def shipping_report(self, date_from, date_to):
        """區間內已完成出貨的彙總：總單數／總件數、依商品、依分店。"""
        rng = (f"{date_from} 00:00:00", f"{date_to} 23:59:59")
        header = self.cursor.execute(
            """
            SELECT COUNT(*) AS cnt, COALESCE(SUM(total_qty), 0) AS qty FROM (
                SELECT so.order_no, SUM(oi.required_qty) AS total_qty
                FROM shipping_orders so
                JOIN shipping_order_items oi ON oi.order_no = so.order_no
                WHERE so.status='已完成' AND so.packed_at BETWEEN ? AND ?
                GROUP BY so.order_no
            )
            """,
            rng,
        ).fetchone()
        by_product = self.cursor.execute(
            """
            SELECT oi.barcode, oi.product_name, COALESCE(p.sku, '') AS sku,
                   SUM(oi.required_qty) AS qty, COUNT(DISTINCT so.order_no) AS orders
            FROM shipping_orders so
            JOIN shipping_order_items oi ON oi.order_no = so.order_no
            LEFT JOIN products p ON p.barcode = oi.barcode
            WHERE so.status='已完成' AND so.packed_at BETWEEN ? AND ?
            GROUP BY oi.barcode
            ORDER BY qty DESC, oi.product_name
            """,
            rng,
        ).fetchall()
        by_branch = self.cursor.execute(
            """
            SELECT b.code || ' ' || b.name AS branch,
                   COUNT(DISTINCT so.order_no) AS orders, SUM(oi.required_qty) AS qty
            FROM shipping_orders so
            JOIN branches b ON b.id = so.branch_id
            JOIN shipping_order_items oi ON oi.order_no = so.order_no
            WHERE so.status='已完成' AND so.packed_at BETWEEN ? AND ?
            GROUP BY so.branch_id
            ORDER BY qty DESC
            """,
            rng,
        ).fetchall()
        return {
            "order_count": header["cnt"],
            "total_qty": header["qty"],
            "by_product": by_product,
            "by_branch": by_branch,
        }

    def loss_report(self, date_from, date_to):
        """區間內損耗彙總：商品報廢（正式扣帳）、耗材報銷、盤點短少。"""
        rng = (f"{date_from} 00:00:00", f"{date_to} 23:59:59")
        rows = self.cursor.execute(
            """
            SELECT CASE WHEN t.tx_type='報廢正式扣帳' THEN '商品報廢'
                        WHEN t.tx_type='耗材報銷' THEN '耗材報銷'
                        ELSE '盤點短少' END AS loss_type,
                   t.barcode, COALESCE(p.name, t.barcode) AS name,
                   SUM(-t.change_qty) AS qty, COUNT(*) AS cnt
            FROM transactions t
            LEFT JOIN products p ON p.barcode = t.barcode
            WHERE t.timestamp BETWEEN ? AND ?
              AND (t.tx_type IN ('報廢正式扣帳', '耗材報銷')
                   OR (t.tx_type IN ('盤點調整', '動態盤點調整') AND t.change_qty < 0))
            GROUP BY loss_type, t.barcode
            ORDER BY loss_type, qty DESC
            """,
            rng,
        ).fetchall()
        totals = {}
        for row in rows:
            totals[row["loss_type"]] = totals.get(row["loss_type"], 0) + row["qty"]
        return {"rows": rows, "totals": totals}
