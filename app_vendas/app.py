from flask import Flask, request, render_template, redirect, url_for, jsonify
import sqlite3
import pandas as pd
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import os

app = Flask(__name__)
DB_NAME = "vendas.db"
scheduler = BackgroundScheduler()
pdf_save_path = ""
next_run_interval = None

# Função para criar o banco de dados e tabela
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS vendas")
    cursor.execute('''CREATE TABLE IF NOT EXISTS vendas (
                        ID_Venda INTEGER PRIMARY KEY,
                        Data_Venda TEXT,
                        ID_Cliente INTEGER,
                        Nome_Cliente TEXT,
                        Produto TEXT,
                        Quantidade INTEGER,
                        Preco_Unitario REAL,
                        Total_Venda REAL)''')
    conn.commit()
    conn.close()

# Função para gerar o relatório PDF
def generate_report(pdf_name):
    global pdf_save_path
    try:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query("SELECT * FROM vendas", conn)
        conn.close()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"{pdf_name}_{timestamp}.pdf"

        # Define o caminho para salvar o PDF
        pdf_filename = os.path.join(pdf_save_path, pdf_filename) if pdf_save_path else os.path.join(os.getcwd(), pdf_filename)

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.drawString(100, 750, "Relatório de Vendas - " + datetime.now().strftime("%Y-%m-%d"))
        y = 700
        for index, row in df.iterrows():
            c.drawString(100, y, f"{row['Data_Venda']} - Cliente: {row['Nome_Cliente']} - Produto: {row['Produto']} - Total: {row['Total_Venda']}")
            y -= 20
        c.save()

        buffer.seek(0)
        with open(pdf_filename, "wb") as f:
            f.write(buffer.read())
    except Exception as e:
        print(f"Erro ao gerar o relatório: {e}")

# Endpoint para upload do CSV
@app.route("/", methods=["GET", "POST"])
def upload_file():
    global pdf_save_path, next_run_interval
    if request.method == "POST":
        file = request.files.get("file")
        frequency = request.form["frequency"]
        pdf_name = request.form["pdf_name"].replace(" ", "_")
        pdf_save_path = request.form["pdf_save_path"]

        if file and file.filename.endswith('.csv'):
            try:
                # Verifica se já existe um job agendado e para se existir
                for job in scheduler.get_jobs():
                    scheduler.remove_job(job.id)

                df = pd.read_csv(file, encoding='utf-8')
                expected_columns = ['ID_Venda', 'Data_Venda', 'ID_Cliente', 
                                    'Nome_Cliente', 'Produto', 'Quantidade', 
                                    'Preco_Unitario', 'Total_Venda']
                df.columns = expected_columns
                df = df[expected_columns]

                conn = sqlite3.connect(DB_NAME)
                df.to_sql("vendas", conn, if_exists="replace", index=False)
                conn.close()

                # Define a frequência e adiciona o trabalho ao agendador
                if frequency == "minute":
                    next_run_interval = timedelta(minutes=1)
                    scheduler.add_job(lambda: generate_report(pdf_name), 'interval', minutes=1)
                elif frequency == "hour":
                    next_run_interval = timedelta(hours=1)
                    scheduler.add_job(lambda: generate_report(pdf_name), 'interval', hours=1)
                elif frequency == "day":
                    next_run_interval = timedelta(days=1)
                    scheduler.add_job(lambda: generate_report(pdf_name), 'interval', days=1)
                elif frequency == "month":
                    next_run_interval = timedelta(days=30)
                    scheduler.add_job(lambda: generate_report(pdf_name), 'cron', month='*', day='1')
                elif frequency == "year":
                    next_run_interval = timedelta(days=365)
                    scheduler.add_job(lambda: generate_report(pdf_name), 'cron', month='1', day='1')

                return redirect(url_for("timer"))
            except Exception as e:
                print(f"Erro ao processar o arquivo CSV: {e}")

    return render_template("index.html")

# Endpoint para obter o tempo restante até o próximo relatório
@app.route("/api/time_remaining")
def time_remaining():
    global next_run_interval
    time_remaining = next_run_interval.total_seconds() if next_run_interval else 0

    if scheduler.get_jobs():
        job = scheduler.get_jobs()[-1]
        if hasattr(job, 'next_run_time') and job.next_run_time:
            now = datetime.now()  # offset-naive
            time_remaining = (job.next_run_time.replace(tzinfo=None) - now).total_seconds()

    return jsonify({'time_remaining': int(time_remaining)})

# Endpoint para exibir o timer
@app.route("/timer")
def timer():
    global next_run_interval
    time_remaining = next_run_interval.total_seconds() if next_run_interval else 0

    if scheduler.get_jobs():
        job = scheduler.get_jobs()[-1]
        if hasattr(job, 'next_run_time') and job.next_run_time:
            now = datetime.now()  # offset-naive
            time_remaining = (job.next_run_time.replace(tzinfo=None) - now).total_seconds()

    return render_template("timer.html", time_remaining=int(time_remaining))

# Endpoint para parar o agendador e voltar ao upload
@app.route("/stop")
def stop():
    global scheduler
    if scheduler.running:
        scheduler.shutdown(wait=False)  # Espera que os jobs em execução terminem
    init_db()  # Reinicializa o banco de dados
    return redirect(url_for("upload_file"))

# Endpoint para consultar dados de vendas
@app.route("/api/vendas", methods=["GET"])
def vendas():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM vendas", conn)
    conn.close()
    return df.to_json(orient="records")

# Endpoint para análise básica
@app.route("/api/analise", methods=["GET"])
def analise():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM vendas", conn)
    conn.close()

    analise = {
        "total_vendas": df["Total_Venda"].sum(),
        "total_produtos_vendidos": df["Quantidade"].sum(),
        "media_valor_venda": df["Total_Venda"].mean()
    }
    return jsonify(analise)

if __name__ == "__main__":
    init_db()
    if not scheduler.running:
        scheduler.start()
    app.run(debug=True)
