import socket
import threading
import time
import hashlib
import requests

# Configurações do Telegram
TELEGRAM_TOKEN = "8022479701:AAG0FL1L59S3WBtYRrVmiWu4aVNaJIdXeMc"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Configurações do servidor
HOST = 'localhost'
PORTA = 31471

# Estruturas de dados para armazenar transações e clientes
transacoes_pendentes = []  # Lista para armazenar transações pendentes de validação
transacoes_validadas = []  # Lista para armazenar transações validadas
clientes = {}  # Dicionário para armazenar informações dos clientes
tamanho_janela = 1000000  # Tamanho da janela de validação

# Lock para evitar condições de corrida durante a validação do nonce
validacao_lock = threading.Lock()

# Função para adicionar uma nova transação
def adicionar_transacao(transacao, bits_zero):
    transacoes_pendentes.append((transacao, bits_zero))
    print(f"Transação '{transacao}' adicionada com {bits_zero} bits zero.")

# Função para distribuir transações para clientes
def distribuir_transacao(conexao_cliente, endereco_cliente):
    if len(transacoes_pendentes) > 0:
        transacao, bits_zero = transacoes_pendentes[0]  # Pega a primeira transação da lista
        clientes_validando = len([c for c in clientes.values() if c.get('transacao') == transacao])
        inicio_janela = clientes_validando * tamanho_janela
        fim_janela = (clientes_validando + 1) * tamanho_janela - 1
        
        # Codifica os números em big endian
        bits_zero_bytes = bits_zero.to_bytes(4, 'big')
        clientes_validando_bytes = clientes_validando.to_bytes(4, 'big')
        inicio_janela_bytes = inicio_janela.to_bytes(8, 'big')
        fim_janela_bytes = fim_janela.to_bytes(8, 'big')
        
        # Envia a transação, bits zero, número de clientes validando e janela de validação
        resposta = (
            len(transacao).to_bytes(2, 'big') + transacao.encode('utf-8') +
            bits_zero_bytes + clientes_validando_bytes + inicio_janela_bytes + fim_janela_bytes
        )
        conexao_cliente.sendall(resposta)
        
        # Atualiza o estado do cliente
        clientes[endereco_cliente] = {
            'transacao': transacao,
            'inicio_janela': inicio_janela,
            'fim_janela': fim_janela,
            'ultima_solicitacao': time.time(),
            'conexao': conexao_cliente  # Armazena a conexão do cliente
        }
    else:
        # Não há transações pendentes
        conexao_cliente.sendall(b"SEM_TRANSACOES")

# Função para verificar se o nonce é válido
def verificar_nonce(transacao, nonce, bits_zero):
    # Concatena o nonce com a transação e calcula o hash SHA256
    dados = nonce + transacao.encode('utf-8')
    hash_resultado = hashlib.sha256(dados).hexdigest()
    
    # Verifica se o hash começa com a quantidade de bits zero esperada
    return hash_resultado.startswith('0' * bits_zero)

# Função para validar a transação
def validar_transacao(conexao_cliente, endereco_cliente, nonce):
    with validacao_lock:  # Usa o lock para evitar condições de corrida
        if endereco_cliente not in clientes:
            return False
        
        transacao = clientes[endereco_cliente]['transacao']
        bits_zero = next(bz for trans, bz in transacoes_pendentes if trans == transacao)
        
        # Verifica se o nonce é válido
        if verificar_nonce(transacao, nonce, bits_zero):
            # Adiciona a transação à lista de validadas
            transacoes_validadas.append((transacao, nonce, endereco_cliente))
            # Remove a transação da lista de pendentes
            transacoes_pendentes[:] = [(trans, bz) for trans, bz in transacoes_pendentes if trans != transacao]
            
            # Notifica todos os clientes para parar a mineração
            for cliente, info in list(clientes.items()):
                if cliente != endereco_cliente:
                    try:
                        info['conexao'].sendall(b"PARAR_MINERACAO")
                    except Exception as e:
                        print(f"Falha ao notificar cliente {cliente}: {e}")
                        # Remove o cliente se a conexão falhar
                        if cliente in clientes:
                            del clientes[cliente]
            
            # Notifica o cliente vencedor
            conexao_cliente.sendall(b"VALIDACAO_SUCESSO")
            return True
        else:
            # Notifica o cliente que o nonce é inválido
            conexao_cliente.sendall(b"NONCE_INVALIDO")
            return False

# Função para gerenciar a conexão com o cliente
def gerenciar_cliente(conexao_cliente, endereco_cliente):
    print(f'Novo cliente conectado: {endereco_cliente}')
    clientes[endereco_cliente] = {
        'conexao': conexao_cliente,
        'ultima_solicitacao': time.time()
    }
    
    while True:
        try:
            # Recebe o tipo de solicitação (2 bytes)
            tipo_solicitacao = conexao_cliente.recv(2)
            if not tipo_solicitacao:
                break
            
            tipo_solicitacao = int.from_bytes(tipo_solicitacao, 'big')
            
            if tipo_solicitacao == 1:  # SOLICITAR_TRANSACAO
                distribuir_transacao(conexao_cliente, endereco_cliente)
            elif tipo_solicitacao == 2:  # VALIDAR_TRANSACAO
                nonce = conexao_cliente.recv(4)  # Nonce é 4 bytes
                validar_transacao(conexao_cliente, endereco_cliente, nonce)
            else:
                conexao_cliente.sendall(b"SOLICITACAO_INVALIDA")
            
            # Atualiza o tempo da última solicitação
            clientes[endereco_cliente]['ultima_solicitacao'] = time.time()
        except Exception as e:
            print(f"Erro ao processar solicitação do cliente {endereco_cliente}: {e}")
            break
    
    print(f"Cliente {endereco_cliente} desconectado.")
    if endereco_cliente in clientes:
        del clientes[endereco_cliente]
    conexao_cliente.close()

# Função para monitorar clientes inativos
def monitorar_clientes():
    while True:
        time.sleep(60)  # Verifica a cada 60 segundos
        tempo_atual = time.time()
        for endereco_cliente in list(clientes.keys()):
            if tempo_atual - clientes[endereco_cliente]['ultima_solicitacao'] > 60:
                print(f"Fechando conexão com cliente inativo: {endereco_cliente}")
                if endereco_cliente in clientes:
                    del clientes[endereco_cliente]

# Função para interação com o usuário
def interacao_usuario():
    while True:
        comando = input("> ")
        if comando == "/newtrans":
            transacao = input("Informe a transação: ")
            bits_zero = int(input("Informe o número de bits zero esperados: "))
            adicionar_transacao(transacao, bits_zero)
        elif comando == "/validtrans":
            print("Transações validadas:")
            if len(transacoes_validadas) == 0:
                print("Nenhuma transação validada até o momento.")
            else:
                for trans, nonce, cliente in transacoes_validadas:
                    print(f"Transação: {trans}, Nonce: {nonce}, Validado por: {cliente}")
        elif comando == "/pendtrans":
            print("Transações pendentes:")
            if len(transacoes_pendentes) == 0:
                print("Nenhuma transação pendente no momento.")
            else:
                for trans, bits_zero in transacoes_pendentes:
                    clientes_validando = [cliente for cliente, info in clientes.items() if info.get('transacao') == trans]
                    print(f"Transação: {trans}, Bits zero: {bits_zero}, Clientes validando: {clientes_validando}")
        elif comando == "/clients":
            print("Clientes conectados:")
            if len(clientes) == 0:
                print("Nenhum cliente conectado no momento.")
            else:
                for endereco_cliente, info in clientes.items():
                    transacao = info.get('transacao', 'Nenhuma')
                    inicio_janela = info.get('inicio_janela', 0)
                    fim_janela = info.get('fim_janela', 0)
                    print(f"Cliente: {endereco_cliente}, Transação: {transacao}, Janela: {inicio_janela}-{fim_janela}")
        else:
            print("Comando inválido. Comandos disponíveis: /newtrans, /validtrans, /pendtrans, /clients")

# Função para interação com o Telegram
def interacao_telegram():
    offset = 0
    while True:
        try:
            # Obtém as atualizações do Telegram
            response = requests.get(f"{TELEGRAM_API_URL}/getUpdates", params={"offset": offset, "timeout": 30})
            updates = response.json().get("result", [])
            
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message", {})
                chat_id = message.get("chat", {}).get("id")
                text = message.get("text", "").strip()
                
                if text == "/validtrans":
                    resposta = "Transações validadas:\n"
                    if len(transacoes_validadas) == 0:
                        resposta += "Nenhuma transação validada até o momento."
                    else:
                        for trans, nonce, cliente in transacoes_validadas:
                            resposta += f"Transação: {trans}, Nonce: {nonce}, Validado por: {cliente}\n"
                    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": resposta})
                
                elif text == "/pendtrans":
                    resposta = "Transações pendentes:\n"
                    if len(transacoes_pendentes) == 0:
                        resposta += "Nenhuma transação pendente no momento."
                    else:
                        for trans, bits_zero in transacoes_pendentes:
                            clientes_validando = [cliente for cliente, info in clientes.items() if info.get('transacao') == trans]
                            resposta += f"Transação: {trans}, Bits zero: {bits_zero}, Clientes validando: {clientes_validando}\n"
                    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": resposta})
                
                elif text == "/clients":
                    resposta = "Clientes conectados:\n"
                    if len(clientes) == 0:
                        resposta += "Nenhum cliente conectado no momento."
                    else:
                        for endereco_cliente, info in clientes.items():
                            transacao = info.get('transacao', 'Nenhuma')
                            inicio_janela = info.get('inicio_janela', 0)
                            fim_janela = info.get('fim_janela', 0)
                            resposta += f"Cliente: {endereco_cliente}, Transação: {transacao}, Janela: {inicio_janela}-{fim_janela}\n"
                    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": resposta})
                
                else:
                    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "Comando inválido. Comandos disponíveis: /validtrans, /pendtrans, /clients"})
        
        except Exception as e:
            print(f"Erro ao processar mensagem do Telegram: {e}")

# Função principal do servidor
def main():
    try:
        # Cria o socket do servidor
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, PORTA))
        sock.listen()
        print(f"Servidor escutando em {HOST}:{PORTA}...")
    except OSError as e:
        print(f"Erro ao iniciar o servidor: {e}")
        sys.exit(2)
    
    # Inicia a thread para monitorar clientes inativos
    threading.Thread(target=monitorar_clientes, daemon=True).start()
    
    # Inicia a thread para interação com o usuário
    threading.Thread(target=interacao_usuario, daemon=True).start()
    
    # Inicia a thread para interação com o Telegram
    threading.Thread(target=interacao_telegram, daemon=True).start()
    
    while True:
        try:
            conexao, endereco = sock.accept()
            threading.Thread(target=gerenciar_cliente, args=(conexao, endereco)).start()
        except Exception as e:
            print(f"Erro ao aceitar conexão: {e}")
            break
    
    sock.close()

if __name__ == "__main__":
    main()
