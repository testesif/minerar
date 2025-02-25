import socket
import sys
import time
from hashlib import sha256

# Configurações do cliente
HOST = 'localhost'  # Endereço do servidor
PORTA = 31471       # Porta do servidor

# Função para calcular o hash SHA256 de uma transação com um nonce
def calcular_hash(nonce, transacao):
    return sha256(nonce.to_bytes(4, 'big') + transacao.encode('utf-8')).hexdigest()

# Função para enviar uma mensagem para o servidor
def enviar_mensagem(conn, mensagem):
    try:
        msg_bytes = mensagem.encode('utf-8')
        len_msg = len(msg_bytes).to_bytes(2, 'big')  # Tamanho da mensagem em 2 bytes (big-endian)
        conn.sendall(len_msg + msg_bytes)  # Envia o tamanho da mensagem + a mensagem
    except Exception as e:
        print(f"Erro ao enviar mensagem para o servidor: {e}")

# Função para receber uma mensagem do servidor
def receber_mensagem(conn):
    try:
        len_msg = conn.recv(2)  # Recebe os 2 bytes do tamanho da mensagem
        if not len_msg:
            return None
        len_msg = int.from_bytes(len_msg, 'big')
        msg = conn.recv(len_msg).decode('utf-8')
        return msg
    except Exception as e:
        print(f"Erro ao receber mensagem do servidor: {e}")
        return None

# Função principal do cliente
def main():
    try:
        # Conecta ao servidor
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.connect((HOST, PORTA))
        print(f"Conectado ao servidor {HOST}:{PORTA}.")
    except Exception as e:
        print(f"Erro ao conectar ao servidor: {e}")
        sys.exit(1)

    while True:
        try:
            # Solicita uma transação ao servidor
            enviar_mensagem(conn, "SOLICITAR_TRANSACAO")
            resposta = receber_mensagem(conn)

            if resposta == "SEM_TRANSACOES":
                print("Não há transações disponíveis no momento. Aguardando 10 segundos...")
                time.sleep(10)  # Aguarda 10 segundos antes de solicitar novamente
                continue

            # Processa a resposta do servidor
            if resposta.startswith("TRANSACAO:"):
                _, transacao, bits_zero, num_clientes, inicio_janela, fim_janela = resposta.split(":")
                bits_zero = int(bits_zero)
                inicio_janela = int(inicio_janela)
                fim_janela = int(fim_janela)

                print(f"Validando transação: {transacao}")
                print(f"Bits zero esperados: {bits_zero}")
                print(f"Janela de validação: {inicio_janela} a {fim_janela}")

                # Tenta encontrar o nonce válido dentro da janela de validação
                for nonce in range(inicio_janela, fim_janela + 1):
                    hash_resultado = calcular_hash(nonce, transacao)
                    if hash_resultado.startswith("0" * bits_zero):
                        print(f"Nonce encontrado: {nonce}")
                        enviar_mensagem(conn, f"NONCE_ENCONTRADO:{nonce}:{transacao}")
                        break
                else:
                    print("Nonce não encontrado na janela de validação.")
            else:
                print(f"Resposta inesperada do servidor: {resposta}")

            # Aguarda 1 segundo antes de solicitar uma nova transação
            time.sleep(1)

        except Exception as e:
            print(f"Erro durante a execução do cliente: {e}")
            break

    # Fecha a conexão com o servidor
    print("Fechando conexão com o servidor.")
    conn.close()

if __name__ == "__main__":
    main()
