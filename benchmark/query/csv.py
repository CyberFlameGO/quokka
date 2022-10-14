from pyspark.sql.types import StructType, StructField, FloatType, LongType, DecimalType, IntegerType, StringType, DateType, BooleanType

schema_lineitem = StructType()\
    .add("l_orderkey",LongType(),True)\
    .add("l_partkey",LongType(),True)\
    .add("l_suppkey",LongType(),True)\
    .add("l_linenumber",IntegerType(),True)\
    .add("l_quantity",DecimalType(10,2),True)\
    .add("l_extendedprice",DecimalType(10,2),True)\
    .add("l_discount",DecimalType(10,2),True)\
    .add("l_tax",DecimalType(10,2),True)\
    .add("l_returnflag",StringType(),True)\
    .add("l_linestatus",StringType(),True)\
    .add("l_shipdate",DateType(),True)\
    .add("l_commitdate",DateType(),True)\
    .add("l_receiptdate",DateType(),True)\
    .add("l_shipinstruct",StringType(),True)\
    .add("l_shipmode",StringType(),True)\
    .add("l_comment",StringType(),True)\
    .add("l_extra",StringType(),True)

schema_orders = StructType()\
    .add("o_orderkey",LongType(),True)\
    .add("o_custkey",LongType(),True)\
    .add("o_orderstatus",StringType(),True)\
    .add("o_totalprice",DecimalType(10,2),True)\
    .add("o_orderdate",DateType(),True)\
    .add("o_orderpriority",StringType(),True)\
    .add("o_clerk",StringType(),True)\
    .add("o_shippriority",IntegerType(),True)\
    .add("o_comment",StringType(),True)\
    .add("o_extra",StringType(),True)

schema_customers = StructType()\
    .add("c_custkey", LongType(), True)\
    .add("c_name", StringType(), True)\
    .add("c_address", StringType(), True)\
    .add("c_nationkey", LongType(), True)\
    .add("c_phone", StringType(), True)\
    .add("c_acctbal", DecimalType(10,2),True)\
    .add("c_mktsegment", StringType(), True)\
    .add("c_comment", StringType(), True)

schema_supplier = StructType([StructField("s_suppkey",LongType(),False),StructField("s_name",StringType(),True),StructField("s_address",StringType(),True),StructField("s_nationkey",LongType(),False),StructField("s_phone",StringType(),True),StructField("s_acctbal",DecimalType(10,2),True),StructField("s_comment",StringType(),True)])

schema_partsupp = StructType([StructField("ps_partkey",LongType(),False),StructField("ps_suppkey",LongType(),False),StructField("ps_availqty",IntegerType(),True),StructField("ps_supplycost",DecimalType(10,2),True),StructField("ps_comment",StringType(),True)])

schema_nation = StructType([StructField("n_nationkey",LongType(),False),StructField("n_name",StringType(),False),StructField("n_regionkey",LongType(),False),StructField("n_comment",StringType(),True)])

schema_region = StructType([StructField("r_regionkey",LongType(),False),StructField("r_name",StringType(),True),StructField("r_comment",StringType(),True)])



df_lineitem = spark.read.option("header", "false").option("delimiter","|")\
            .schema(schema_lineitem)\
            .csv("s3://tpc-h-csv/lineitem/lineitem.tbl.1")
df_orders = spark.read.option("header", "false").option("delimiter","|")\
        .schema(schema_orders)\
        .csv("s3://tpc-h-csv/orders/orders.tbl.1")
df_customers = spark.read.option("header", "false").option("delimiter","|")\
        .schema(schema_customers)\
        .csv("s3://tpc-h-csv/customer/customer.tbl.1")
df_partsupp = spark.read.option("header", "false").option("delimiter","|")\
            .schema(schema_partsupp)\
            .csv("s3://tpc-h-csv/partsupp/partsupp.tbl.1")
df_part = spark.read.option("header", "false").option("delimiter","|")\
        .schema(schema_part)\
        .csv("s3://tpc-h-csv/part/part.tbl.1")
df_supplier = spark.read.option("header", "false").option("delimiter","|")\
        .schema(schema_supplier)\
        .csv("s3://tpc-h-csv/supplier/supplier.tbl.1")
df_region = spark.read.option("header", "false").option("delimiter","|")\
            .schema(schema_region)\
            .csv("s3://tpc-h-csv/region/region.tbl.1")
df_nation = spark.read.option("header", "false").option("delimiter","|")\
        .schema(schema_nation)\
        .csv("s3://tpc-h-csv/nation/nation.tbl.1")


df_lineitem.createOrReplaceTempView("lineitem")
df_orders.createOrReplaceTempView("orders")
df_customer.createOrReplaceTempView("customer")
df_partsupp.createOrReplaceTempView("partsupp")
df_part.createOrReplaceTempView("part")
df_region.createOrReplaceTempView("region")
df_nation.createOrReplaceTempView("nation")
df_supplier.createOrReplaceTempView("supplier")

query1 = """
select
        l_returnflag,
        l_linestatus,
        sum(l_quantity) as sum_qty,
        sum(l_extendedprice) as sum_base_price,
        sum(l_extendedprice * (1 - l_discount)) as sum_disc_price,
        sum(l_extendedprice * (1 - l_discount) * (1 + l_tax)) as sum_charge,
        avg(l_quantity) as avg_qty,
        avg(l_extendedprice) as avg_price,
        avg(l_discount) as avg_disc,
        count(*) as count_order
from
        lineitem
where
        l_shipdate <= date '1998-12-01' - interval '90' day
group by
        l_returnflag,
        l_linestatus
order by
        l_returnflag,
        l_linestatus
"""

query2 = """
select
        s_acctbal,
        s_name,
        n_name,
        p_partkey,
        p_mfgr,
        s_address,
        s_phone,
        s_comment
from
        part,
        supplier,
        partsupp,
        nation,
        region
where
        p_partkey = ps_partkey
        and s_suppkey = ps_suppkey
        and p_size = 15
        and p_type like '%BRASS'
        and s_nationkey = n_nationkey
        and n_regionkey = r_regionkey
        and r_name = 'EUROPE'
        and ps_supplycost = (
                select
                        min(ps_supplycost)
                from
                        partsupp,
                        supplier,
                        nation,
                        region
                where
                        p_partkey = ps_partkey
                        and s_suppkey = ps_suppkey
                        and s_nationkey = n_nationkey
                        and n_regionkey = r_regionkey
                        and r_name = 'EUROPE'
        )
order by
        s_acctbal desc,
        n_name,
        s_name,
        p_partkey
limit
        100
"""

query3 = """
select
        l_orderkey,
        sum(l_extendedprice * (1 - l_discount)) as revenue,
        o_orderdate,
        o_shippriority
from
        customer,
        orders,
        lineitem
where
        c_mktsegment = 'BUILDING'
        and c_custkey = o_custkey
        and l_orderkey = o_orderkey
        and o_orderdate < date '1995-03-15'
        and l_shipdate > date '1995-03-15'
group by
        l_orderkey,
        o_orderdate,
        o_shippriority
order by
        revenue desc,
        o_orderdate
limit
        10
"""

query4 = """
select
        o_orderpriority,
        count(*) as order_count
from
        orders
where
        o_orderdate >= date '1993-07-01'
        and o_orderdate < date '1993-07-01' + interval '3' month
        and exists (
                select
                        *
                from
                        lineitem
                where
                        l_orderkey = o_orderkey
                        and l_commitdate < l_receiptdate
        )
group by
        o_orderpriority
order by
        o_orderpriority
"""

query5 = """
select
        n_name,
        sum(l_extendedprice * (1 - l_discount)) as revenue
from
        customer,
        orders,
        lineitem,
        supplier,
        nation,
        region
where
        c_custkey = o_custkey
        and l_orderkey = o_orderkey
        and l_suppkey = s_suppkey
        and c_nationkey = s_nationkey
        and s_nationkey = n_nationkey
        and n_regionkey = r_regionkey
        and r_name = 'ASIA'
        and o_orderdate >= date '1994-01-01'
        and o_orderdate < date '1994-01-01' + interval '1' year
group by
        n_name
order by
        revenue desc
"""

query6 = """
select
        sum(l_extendedprice * l_discount) as revenue
from
        lineitem
where
        l_shipdate >= date '1994-01-01'
        and l_shipdate < date '1994-01-01' + interval '1' year
        and l_discount between 0.06 - 0.01 and 0.06 + 0.01
        and l_quantity < 24

"""

query7 = """
select
        supp_nation,
        cust_nation,
        l_year,
        sum(volume) as revenue
from
        (
                select
                        n1.n_name as supp_nation,
                        n2.n_name as cust_nation,
                        extract(year from l_shipdate) as l_year,
                        l_extendedprice * (1 - l_discount) as volume
                from
                        supplier,
                        lineitem,
                        orders,
                        customer,
                        nation n1,
                        nation n2
                where
                        s_suppkey = l_suppkey
                        and o_orderkey = l_orderkey
                        and c_custkey = o_custkey
                        and s_nationkey = n1.n_nationkey
                        and c_nationkey = n2.n_nationkey
                        and (
                                (n1.n_name = 'FRANCE' and n2.n_name = 'GERMANY')
                                or (n1.n_name = 'GERMANY' and n2.n_name = 'FRANCE')
                        )
                        and l_shipdate between date '1995-01-01' and date '1996-12-31'
        ) as shipping
group by
        supp_nation,
        cust_nation,
        l_year
order by
        supp_nation,
        cust_nation,
        l_year
"""

query12 = """
select
        l_shipmode,
        sum(case
                when o_orderpriority = '1-URGENT'
                        or o_orderpriority = '2-HIGH'
                        then 1
                else 0
        end) as high_line_count,
        sum(case
                when o_orderpriority <> '1-URGENT'
                        and o_orderpriority <> '2-HIGH'
                        then 1
                else 0
        end) as low_line_count
from
        orders,
        lineitem
where
        o_orderkey = l_orderkey
        and l_shipmode in ('MAIL', 'SHIP')
        and l_commitdate < l_receiptdate
        and l_shipdate < l_commitdate
        and l_receiptdate >= date '1994-01-01'
        and l_receiptdate < date '1994-01-01' + interval '1' year
group by
        l_shipmode
order by
        l_shipmode
"""
import time

start = time.time(); result = spark.sql(query12).collect(); print("QUERY TOOK", time.time() - start)
