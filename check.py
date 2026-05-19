import psycopg2

conn = psycopg2.connect("YOUR_CONNECTION_STRING_HERE")
conn.autocommit = True
cur = conn.cursor()
cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")
print(cur.fetchone())
conn.close()
