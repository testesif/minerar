import socket
import threading
import sys
import time
from hashlib import sha256

# Configurações do servidor
HOST = 'localhost'  # Endereço do servidor
PORTA = 31471       # Porta do servidor

# Variáveis globais
transacoes_pendentes = []  # Lista de transações pendentes de validação
transacoes_validadas = []  # Lista de transações já validadas
clientes_conectados = {}   # Dicionário para armazenar informações dos clientes
bits_zero = 0              # Número de bits zero iniciais esperados no hash
janela_validacao = 1000000 # Tamanho da janela de validação para cada cliente

# Função para calcular o hash SHA256 de uma transação com um nonce
def calcular_hash(nonce, transacao):
    return sha256(nonce.to_bytes(4, 'big') + transacao.encode('utf-8')).hexdigest()

# Função para enviar uma mensagem para um cliente
def enviar_mensagem(conn, mensagem):
    try:
        msg_bytes = mensagem.encode('utf-8')
        len_msg = len(msg_bytes).to_bytes(2, 'big')  # Tamanho da mensagem em 2 bytes (big-endian)
        conn.sendall(len_msg + msg_bytes)  # Envia o tamanho da mensagem + a mensagem
    except Exception as e:
        print(f"Erro ao enviar mensagem para o cliente: {e}")

# Função para broadcast de mensagens para todos os clientes
def broadcast_mensagem(mensagem, conn_excecao=None):
    for conn in clientes_conectados:
        if conn != conn_excecao:  # Não envia a mensagem para o próprio cliente
            enviar_mensagem(conn, mensagem)

# Função para processar as conexões dos clientes
def processar_cliente(conn, addr):
    print(f'Novo cliente conectado: {addr}')
    clientes_conectados[conn] = {"nome": f"Cliente {addr}", "transacao": None, "intervalo": None}

    while True:
        try:
            # Recebe a solicitação do cliente
            len_msg = conn.recv(2)  # Recebe os 2 bytes do tamanho da mensagem
            if not len_msg:
                break
            len_msg = int.from_bytes(len_msg, 'big')
            msg = conn.recv(len_msg).decode('utf-8')

            if msg == "SOLICITAR_TRANSACAO":
                if transacoes_pendentes:
                    transacao = transacoes_pendentes[0]  # Pega a primeira transação pendente
                    num_clientes = len([c for c in clientes_conectados.values() if c["transacao"] == transacao])
                    intervalo_inicio = num_clientes * janela_validacao
                    intervalo_fim = (num_clientes + 1) * janela_validacao - 1

                    # Envia a transação, bits zero, número de clientes e intervalo de validação
                    resposta = f"TRANSACAO:{transacao}:{bits_zero}:{num_clientes}:{intervalo_inicio}:{intervalo_fim}"
                    enviar_mensagem(conn, resposta)

                    # Atualiza as informações do cliente
                    clientes_conectados[conn]["transacao"] = transacao
                    clientes_conectados[conn]["intervalo"] = (intervalo_inicio, intervalo_fim)
                else:
                    enviar_mensagem(conn, "SEM_TRANSACOES")
                    time.sleep(10)  # Aguarda 10 segundos antes de solicitar novamente
            elif msg.startswith("NONCE_ENCONTRADO:"):
                # Processa o nonce encontrado pelo cliente
                _, nonce, transacao = msg.split(":")
                nonce = int(nonce)
                hash_resultado = calcular_hash(nonce, transacao)
                if hash_resultado.startswith("0" * bits_zero):
                    # Adiciona a transação à lista de validadas
                    transacoes_validadas.append((transacao, nonce, clientes_conectados[conn]["nome"]))
                    transacoes_pendentes.remove(transacao)  # Remove a transação da lista de pendentes
                    broadcast_mensagem(f"TRANSACAO_VALIDADA:{transacao}:{nonce}:{clientes_conectados[conn]['nome']}")
                else:
                    enviar_mensagem(conn, "NONCE_INVALIDO")
        except Exception as e:
            print(f"Erro no cliente {addr}: {e}")
            break

    # Remove o cliente da lista de conectados
    print(f"Cliente {addr} desconectado.")
    del clientes_conectados[conn]
    conn.close()

# Função para interação com o usuário
def interacao_usuario():
    global bits_zero
    while True:
        comando = input("> ")
        if comando == "/newtrans":
            transacao = input("Digite a nova transação: ")
            transacoes_pendentes.append(transacao)
            print(f"Transação '{transacao}' adicionada às pendentes.")
        elif comando == "/validtrans":
            print("Transações validadas:")
            for transacao, nonce, cliente in transacoes_validadas:
                print(f"Transação: {transacao}, Nonce: {nonce}, Validado por: {cliente}")
        elif comando == "/pendtrans":
            print("Transações pendentes:")
            for transacao in transacoes_pendentes:
                clientes_validando = [c["nome"] for c in clientes_conectados.values() if c["transacao"] == transacao]
                print(f"Transação: {transacao}, Clientes validando: {clientes_validando}")
        elif comando == "/clients":
            print("Clientes conectados:")
            for conn, info in clientes_conectados.items():
                print(f"{info['nome']} - Transação: {info['transacao']}, Intervalo: {info['intervalo']}")
        elif comando == "/setbits":
            bits_zero = int(input("Digite o número de bits zero iniciais: "))
            print(f"Bits zero iniciais definidos para {bits_zero}.")
        else:
            print("Comando não reconhecido.")

# Função para iniciar o servidor
def iniciar_servidor():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, PORTA))
        sock.listen()
        print(f"Servidor iniciado em {HOST}:{PORTA}. Aguardando conexões...")
        return sock
    except Exception as e:
        print(f"Erro ao iniciar o servidor: {e}")
        sys.exit(1)

# Função principal
def main():
    sock = iniciar_servidor()

    # Inicia a thread de interação com o usuário
    threading.Thread(target=interacao_usuario, daemon=True).start()

    while True:
        try:
            conn, addr = sock.accept()
            threading.Thread(target=processar_cliente, args=(conn, addr)).start()
        except KeyboardInterrupt:
            print("Servidor encerrado.")
            break

    sock.close()

if __name__ == "__main__":
    main()
