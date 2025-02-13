from flask import Flask, jsonify, request, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from collections import defaultdict
import os
import logging

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ponto.db'
db = SQLAlchemy(app)

# Configuração de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MODELO PARA A TABELA DE REGISTROS DE PONTO
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

# CRIA O BANCO DE DADOS (EXECUTE APENAS UMA VEZ)
with app.app_context():
    db.create_all()

# ROTA PARA SERVIR O ARQUIVO INDEX.HTML
@app.route("/")
def index():
    return send_from_directory(os.path.dirname(__file__), "index.html")

# FUNÇÃO PARA VALIDAR HORÁRIOS
def validar_horario(horario):
    try:
        datetime.strptime(horario, "%H:%M")
        return True
    except ValueError:
        return False

# FUNÇÃO PARA FORMATAR TEMPO (timedelta para HH:MM)
def formatar_tempo(td):
    total_minutos = int(td.total_seconds() // 60)
    horas = total_minutos // 60
    minutos = total_minutos % 60
    return f"{horas:02}:{minutos:02}"

# ROTA PARA REGISTRAR NOVOS PONTOS
@app.route("/registrar", methods=["POST"])
def registrar_ponto():
    dados = request.json
    if not all(validar_horario(dados[campo]) for campo in ["entrada", "saida_almoco", "retorno_almoco", "saida"]):
        abort(400, description="Formato de horário inválido.")

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
        # Converte os horários para datetime para facilitar cálculos
        entrada_dt = datetime.combine(datetime.today(), entrada)
        saida_almoco_dt = datetime.combine(datetime.today(), saida_almoco)
        retorno_almoco_dt = datetime.combine(datetime.today(), retorno_almoco)
        saida_dt = datetime.combine(datetime.today(), saida)

        # Calcula o tempo total trabalhado (descontando o almoço)
        horas_trabalhadas = (saida_dt - entrada_dt) - (retorno_almoco_dt - saida_almoco_dt)

        # Converte o saldo para horas e minutos
        saldo = formatar_tempo(horas_trabalhadas)

        # Calcula as horas extras (saldo - 8 horas)
        horas_extras = horas_trabalhadas - timedelta(hours=8)
        if horas_extras.total_seconds() < 0:
            extra = "00:00"  # Não há horas extras
        else:
            extra = formatar_tempo(horas_extras)

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
            obs=dados.get("obs", "")
        )
        db.session.add(novo_registro)
        db.session.commit()
        return jsonify({"message": "Registro salvo com sucesso!"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Erro ao salvar registro: {str(e)}"}), 500

# ROTA PARA OBTER TODOS OS DADOS
@app.route("/dados", methods=["GET"])
def obter_dados():
    registros = RegistroPonto.query.all()

    # Formata os dados para retorno
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

# ROTA PARA OBTER DADOS DE SALDO DE HORAS
@app.route("/dados/saldo", methods=["GET"])
def obter_saldo_horas():
    registros = RegistroPonto.query.all()

    # Calcula o saldo acumulado total
    saldo_total = 0
    for registro in registros:
        horas, minutos = map(int, registro.saldo.split(':'))
        horas_trabalhadas = horas + minutos / 60  # Converte para horas decimais
        saldo_diario = horas_trabalhadas - 8 #Subtrai a jornada de 8 horas
        saldo_total += saldo_diario #Acumula o saldo

    #Separa horas sobrando e horas faltantes
    horas_sobrando = max(saldo_total, 0) #Horas sobrando (apenas valores positivos)
    horas_faltantes = abs(min(saldo_total, 0)) #Horas faltantes (apenas valores negativos)

    # Retorna o saldo acumulado total
    return jsonify({
        "horas_sobrando": horas_sobrando,
        "horas_faltantes": horas_faltantes
    }), 200

# ROTA PARA OBTER OU EDITAR UM REGISTRO ESPECÍFICO
@app.route("/dados/<int:id>", methods=["GET", "PUT"])
def obter_ou_editar_registro(id):
    registro = RegistroPonto.query.get(id)
    if not registro:
        return jsonify({"message": "Registro não encontrado"}), 404

    if request.method == "GET":
        # Retorna os dados do registro
        return jsonify({
            "id": registro.id,
            "data": registro.data.strftime("%Y-%m-%d"),  # Formato yyyy-MM-dd
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
            # Valida o formato da data (espera yyyy-MM-dd)
            data = datetime.strptime(dados["data"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"message": "Formato de data inválido. Use yyyy-MM-dd."}), 400

        try:
            # Valida os horários
            entrada = datetime.strptime(dados["entrada"], "%H:%M").time()
            saida_almoco = datetime.strptime(dados["saida_almoco"], "%H:%M").time()
            retorno_almoco = datetime.strptime(dados["retorno_almoco"], "%H:%M").time()
            saida = datetime.strptime(dados["saida"], "%H:%M").time()
        except ValueError:
            return jsonify({"message": "Formato de horário inválido. Use HH:MM."}), 400

        # Atualiza os campos do registro
        registro.data = data
        registro.entrada = entrada
        registro.saida_almoco = saida_almoco
        registro.retorno_almoco = retorno_almoco
        registro.saida = saida
        registro.obs = dados.get("obs", "")

        # Recalcula o saldo e horas extras
        try:
            horas_trabalhadas = (
                (datetime.combine(datetime.today(), registro.saida) - datetime.combine(datetime.today(), registro.entrada)) -
                (datetime.combine(datetime.today(), registro.retorno_almoco) - datetime.combine(datetime.today(), registro.saida_almoco))
            )
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


# ROTA PARA OBTER DADOS MENSAL
@app.route("/dados/mensal", methods=["GET"])
def obter_dados_mensais():
    registros = RegistroPonto.query.all()

    # Agrupa os registros por mês
    dados_mensais = defaultdict(list)
    for registro in registros:
        mes = registro.data.strftime("%m-%Y")  # Formato: "2025-01"
        saldo = registro.saldo  # Já é uma string no formato HH:MM
        horas, minutos = map(int, saldo.split(':'))
        total_horas = horas + minutos / 60  # Converte para horas decimais
        dados_mensais[mes].append(total_horas)

    # Calcula a média mensal
    medias_mensais = {
        mes: sum(valores) / len(valores)
        for mes, valores in dados_mensais.items()
    }

    return jsonify(medias_mensais), 200

# ROTA PARA EXCLUIR UM REGISTRO
@app.route("/dados/<int:id>", methods=["DELETE"])
def excluir_registro(id):
    registro = RegistroPonto.query.get(id)
    if not registro:
        return jsonify({"message": "Registro não encontrado"}), 404

    db.session.delete(registro)
    db.session.commit()

    logger.info(f"Registro excluído: {registro.id}")
    return jsonify({"message": "Registro excluído com sucesso!"}), 200

# TRATAMENTO DE ERROS
@app.errorhandler(400)
def bad_request(error):
    return jsonify({"message": "Requisição inválida"}), 400

@app.errorhandler(404)
def not_found(error):
    return jsonify({"message": "Recurso não encontrado"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"message": "Erro interno no servidor"}), 500

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)