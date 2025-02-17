from flask import Flask, jsonify, request, send_from_directory, abort, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
from collections import defaultdict
import os
import logging

# Configuração do Flask
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ponto.db'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'uma_chave_segura_padrao')
db = SQLAlchemy(app)

# Configuração do Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Configuração de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Modelo de Usuários
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

# Modelo para a tabela de registros de ponto
class RegistroPonto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    entrada = db.Column(db.Time, nullable=False)
    saida_almoco = db.Column(db.Time, nullable=False)
    retorno_almoco = db.Column(db.Time, nullable=False)
    saida = db.Column(db.Time, nullable=False)
    saldo = db.Column(db.String(5), nullable=False)
    extra = db.Column(db.String(5), nullable=False)
    obs = db.Column(db.String(200))
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

# Cria o banco de dados (execute apenas uma vez)
with app.app_context():
    db.create_all()

# Função para carregar o usuário
@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# Rota para servir o arquivo login.html
@app.route("/login.html")
def login_page():
    return send_from_directory(os.path.dirname(__file__), "login.html")

# Rota para servir o arquivo index.html
@app.route("/index.html")
def index_page():
    return send_from_directory(os.path.dirname(__file__), "index.html")

# Rota raiz (redireciona para login.html se não estiver autenticado)
@app.route("/")
def index():
    if current_user.is_authenticated:
        return send_from_directory(os.path.dirname(__file__), "index.html")
    else:
        return send_from_directory(os.path.dirname(__file__), "login.html")

# Rota para login
@app.route("/login", methods=["POST"])
def login():
    dados = request.json
    usuario = Usuario.query.filter_by(username=dados['username']).first()
    if usuario and usuario.password == dados['password']:
        login_user(usuario)
        return jsonify({"message": "Login realizado com sucesso!"}), 200
    return jsonify({"message": "Usuário ou senha incorretos."}), 401

# Rota para logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return jsonify({"message": "Logout realizado com sucesso!"}), 200

# Rota para registrar usuário
@app.route('/registrar_usuario', methods=['POST'])
def registrar_usuario():
    dados = request.json
    if Usuario.query.filter_by(username=dados['username']).first():
        return jsonify({"message": "Usuário já existe"}), 400
    novo_usuario = Usuario(username=dados['username'], password=dados['password'])
    db.session.add(novo_usuario)
    db.session.commit()
    return jsonify({"message": "Usuário registrado com sucesso"}), 201

# Função para formatar tempo (timedelta para HH:MM)
def formatar_tempo(td):
    total_minutos = int(td.total_seconds() // 60)
    horas = total_minutos // 60
    minutos = total_minutos % 60
    return f"{horas:02}:{minutos:02}"

# Rota para registrar novos pontos
@app.route("/registrar", methods=["POST"])
@login_required
def registrar_ponto():
    dados = request.json

    try:
        data = datetime.strptime(dados["data"], "%Y-%m-%d").date()
        entrada = datetime.strptime(dados["entrada"], "%H:%M").time()
        saida_almoco = datetime.strptime(dados["saida_almoco"], "%H:%M").time()
        retorno_almoco = datetime.strptime(dados["retorno_almoco"], "%H:%M").time()
        saida = datetime.strptime(dados["saida"], "%H:%M").time()
    except ValueError as e:
        return jsonify({"message": f"Formato de data ou horário inválido: {str(e)}"}), 400

    # Cálculo do saldo e horas extras
    try:
        entrada_dt = datetime.combine(datetime.today(), entrada)
        saida_almoco_dt = datetime.combine(datetime.today(), saida_almoco)
        retorno_almoco_dt = datetime.combine(datetime.today(), retorno_almoco)
        saida_dt = datetime.combine(datetime.today(), saida)

        # Lógica para lidar com horários que viram o dia
        if saida_dt < entrada_dt:
            saida_dt += timedelta(days=1)

        horas_trabalhadas = (saida_dt - entrada_dt) - (retorno_almoco_dt - saida_almoco_dt)
        saldo = formatar_tempo(horas_trabalhadas)
        horas_extras = horas_trabalhadas - timedelta(hours=8)
        extra = formatar_tempo(max(horas_extras, timedelta(0)))

    except Exception as e:
        return jsonify({"message": f"Erro ao calcular saldo: {str(e)}"}), 500

    # Salva o registro no banco de dados
    try:
        novo_registro = RegistroPonto(
            data=data,
            entrada=entrada,
            saida_almoco=saida_almoco,
            retorno_almoco=retorno_almoco,
            saida=saida,
            saldo=saldo,
            extra=extra,
            obs=dados.get("obs", ""),
            usuario_id=current_user.id
        )
        db.session.add(novo_registro)
        db.session.commit()
        return jsonify({"message": "Registro salvo com sucesso!"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Erro ao salvar registro: {str(e)}"}), 500

# Rota para obter todos os dados (filtrados por usuário)
@app.route("/dados", methods=["GET"])
@login_required
def obter_dados():
    registros = RegistroPonto.query.filter_by(usuario_id=current_user.id).all()

    dados = [{
        "id": registro.id,
        "data": registro.data.strftime("%d-%m-%Y"),
        "entrada": registro.entrada.strftime("%H:%M"),
        "saida_almoco": registro.saida_almoco.strftime("%H:%M"),
        "retorno_almoco": registro.retorno_almoco.strftime("%H:%M"),
        "saida": registro.saida.strftime("%H:%M"),
        "saldo": registro.saldo,
        "extra": registro.extra,
        "obs": registro.obs
    } for registro in registros]

    return jsonify(dados), 200

# Rota para obter dados de saldo de horas (filtrados por usuário)
@app.route("/dados/saldo", methods=["GET"])
@login_required
def obter_saldo_horas():
    registros = RegistroPonto.query.filter_by(usuario_id=current_user.id).all()

    saldo_total = timedelta(0)
    for registro in registros:
        horas, minutos = map(int, registro.saldo.split(':'))
        saldo_total += timedelta(hours=horas, minutes=minutos)

    horas_sobrando = max(saldo_total, timedelta(0))
    horas_faltantes = abs(min(saldo_total, timedelta(0)))

    return jsonify({
        "horas_sobrando": formatar_tempo(horas_sobrando),
        "horas_faltantes": formatar_tempo(horas_faltantes)
    }), 200

# Rota para obter ou editar um registro específico
@app.route("/dados/<int:id>", methods=["GET", "PUT"])
@login_required
def obter_ou_editar_registro(id):
    registro = RegistroPonto.query.get_or_404(id)

    if registro.usuario_id != current_user.id:
        abort(403)

    if request.method == "GET":
        return jsonify({
            "id": registro.id,
            "data": registro.data.strftime("%Y-%m-%d"),
            "entrada": registro.entrada.strftime("%H:%M"),
            "saida_almoco": registro.saida_almoco.strftime("%H:%M"),
            "retorno_almoco": registro.retorno_almoco.strftime("%H:%M"),
            "saida": registro.saida.strftime("%H:%M"),
            "saldo": registro.saldo,
            "extra": registro.extra,
            "obs": registro.obs
        }), 200

    elif request.method == "PUT":
        dados = request.json

        try:
            data = datetime.strptime(dados["data"], "%Y-%m-%d").date()
            entrada = datetime.strptime(dados["entrada"], "%H:%M").time()
            saida_almoco = datetime.strptime(dados["saida_almoco"], "%H:%M").time()
            retorno_almoco = datetime.strptime(dados["retorno_almoco"], "%H:%M").time()
            saida = datetime.strptime(dados["saida"], "%H:%M").time()
        except ValueError as e:
            return jsonify({"message": f"Formato de data ou horário inválido: {str(e)}"}), 400

        registro.data = data
        registro.entrada = entrada
        registro.saida_almoco = saida_almoco
        registro.retorno_almoco = retorno_almoco
        registro.saida = saida
        registro.obs = dados.get("obs", "")

        try:
            entrada_dt = datetime.combine(datetime.today(), registro.entrada)
            saida_almoco_dt = datetime.combine(datetime.today(), registro.saida_almoco)
            retorno_almoco_dt = datetime.combine(datetime.today(), registro.retorno_almoco)
            saida_dt = datetime.combine(datetime.today(), registro.saida)

            if saida_dt < entrada_dt:
                saida_dt += timedelta(days=1)

            horas_trabalhadas = (saida_dt - entrada_dt) - (retorno_almoco_dt - saida_almoco_dt)
            registro.saldo = formatar_tempo(horas_trabalhadas)
            registro.extra = formatar_tempo(max(horas_trabalhadas - timedelta(hours=8), timedelta(0)))
        except Exception as e:
            return jsonify({"message": f"Erro ao calcular saldo: {str(e)}"}), 500

        try:
            db.session.commit()
            return jsonify({"message": "Registro atualizado com sucesso!"}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"message": f"Erro ao atualizar registro: {str(e)}"}), 500

# Rota para obter dados mensais (filtrados por usuário)
@app.route("/dados/mensal", methods=["GET"])
@login_required
def obter_dados_mensais():
    registros = RegistroPonto.query.filter_by(usuario_id=current_user.id).all()

    dados_mensais = defaultdict(list)
    for registro in registros:
        mes = registro.data.strftime("%m-%Y")
        horas, minutos = map(int, registro.saldo.split(':'))
        total_horas = horas + minutos / 60
        dados_mensais[mes].append(total_horas)

    medias_mensais = {
        mes: sum(valores) / len(valores) if valores else 0
        for mes, valores in dados_mensais.items()
    }

    return jsonify(medias_mensais), 200

# Rota para excluir um registro
@app.route("/dados/<int:id>", methods=["DELETE"])
@login_required
def excluir_registro(id):
    registro = RegistroPonto.query.get_or_404(id)

    if registro.usuario_id != current_user.id:
        abort(403)

    db.session.delete(registro)
    db.session.commit()

    logger.info(f"Registro excluído: {registro.id}")
    return jsonify({"message": "Registro excluído com sucesso!"}), 200

# Tratamento de erros
@app.errorhandler(400)
def bad_request(error):
    return jsonify({"message": "Requisição inválida"}), 400

@app.errorhandler(403)
def forbidden(error):
    return jsonify({"message": "Acesso negado"}), 403

@app.errorhandler(404)
def not_found(error):
    return jsonify({"message": "Recurso não encontrado"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"message": "Erro interno no servidor"}), 500

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
