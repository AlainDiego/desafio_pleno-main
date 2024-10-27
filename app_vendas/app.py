from flask import Flask, request, render_template, redirect, url_for, jsonify
import sqlite3
import pandas as pd
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import matplotlib
matplotlib.use('Agg')  # Força o uso do backend Agg
import matplotlib.pyplot as plt
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

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

# Função para gerar gráficos de análise
def generate_graphs(df):
    image_paths = []
    
    try:
        # Análise 1: Total de Vendas por Cliente
        plt.figure(figsize=(10, 6))
        total_sales_per_client = df.groupby('Nome_Cliente')['Total_Venda'].sum().nlargest(5)
        total_sales_per_client.plot(kind='bar', title='Total de Vendas por Cliente', color='skyblue')
        plt.ylabel('Total de Vendas')
        plt.tight_layout()
        img_path = "total_sales_per_client.png"
        plt.savefig(img_path)
        plt.close()
        image_paths.append(img_path)

        # Análise 2: Total de Vendas por Produto
        plt.figure(figsize=(10, 6))
        total_sales_per_product = df.groupby('Produto')['Total_Venda'].sum().nlargest(5)
        total_sales_per_product.plot(kind='bar', title='Total de Vendas por Produto', color='salmon')
        plt.ylabel('Total de Vendas')
        plt.tight_layout()
        img_path = "total_sales_per_product.png"
        plt.savefig(img_path)
        plt.close()
        image_paths.append(img_path)

        # Análise 3: Quantidade Total Vendida por Produto
        plt.figure(figsize=(10, 6))
        total_quantity_per_product = df.groupby('Produto')['Quantidade'].sum().nlargest(5)
        total_quantity_per_product.plot(kind='bar', title='Quantidade Total Vendida por Produto', color='lightgreen')
        plt.ylabel('Quantidade Vendida')
        plt.tight_layout()
        img_path = "quantity_per_product.png"
        plt.savefig(img_path)
        plt.close()
        image_paths.append(img_path)

        # Análise 4: Desempenho de Vendas ao Longo do Tempo
        df['Data_Venda'] = pd.to_datetime(df['Data_Venda'])
        sales_over_time = df.groupby(df['Data_Venda'].dt.to_period('M'))['Total_Venda'].sum()
        
        plt.figure(figsize=(10, 6))
        sales_over_time.plot(kind='line', title='Desempenho de Vendas ao Longo do Tempo', marker='o')
        plt.ylabel('Total de Vendas')
        plt.xlabel('Data')
        plt.xticks(rotation=45)
        plt.tight_layout()
        img_path = "sales_over_time.png"
        plt.savefig(img_path)
        plt.close()
        image_paths.append(img_path)

    except Exception as e:
        print(f"Erro ao gerar gráficos: {e}")

    return image_paths

# Função para gerar o relatório PDF
def generate_report(pdf_name):
    global pdf_save_path
    try:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query("SELECT * FROM vendas", conn)
        conn.close()

        # Gerar gráficos
        image_paths = generate_graphs(df)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"{pdf_name}_{timestamp}.pdf"

        if pdf_save_path:
            pdf_filename = os.path.join(pdf_save_path, pdf_filename)
        else:
            pdf_filename = os.path.join(os.getcwd(), pdf_filename)

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter  # Tamanho da página
        y = height - 50  # Espaço no topo da página

        for img_path in image_paths:
            img_width = 500  # Largura desejada da imagem
            img_height = 300  # Altura desejada da imagem
            
            # Verificar se a imagem cabe na página
            if y - img_height < 50:  # 50 é o espaço mínimo que deve ser deixado
                c.showPage()  # Adiciona uma nova página ao PDF
                y = height - 50  # Reinicia a posição Y na nova página

            # Adicionar gráfico ao PDF
            c.drawImage(img_path, 50, y - img_height, width=img_width, height=img_height)  # Ajuste o tamanho do gráfico
            y -= img_height + 20  # Ajuste o espaço para o próximo gráfico

        c.save()

        buffer.seek(0)
        with open(pdf_filename, "wb") as f:
            f.write(buffer.read())

        # Remover arquivos temporários
        for img_path in image_paths:
            os.remove(img_path)

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

    next_run_interval = None
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
    global scheduler, pdf_save_path, next_run_interval
    for job in scheduler.get_jobs():
        scheduler.remove_job(job.id)

    init_db()  
    pdf_save_path = ""  
    next_run_interval = None  

    return redirect(url_for("upload_file"))

# Endpoint para consultar dados de vendas
@app.route("/api/vendas", methods=["GET"])
def get_vendas():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vendas")
    vendas = cursor.fetchall()
    conn.close()
    return jsonify(vendas)

if __name__ == "__main__":
    init_db()
    scheduler.start()
    app.run(debug=True)
