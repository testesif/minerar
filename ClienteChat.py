import socket
import threading
import sys
import hashlib

HOST = 'localhost'  
PORT= 31471  
tcp_sock = None  

def enviar_mensagem_get(nome_cliente):   # envia uma mensagem para o servidor solicitando a transação
    nome_cliente = nome_cliente.ljust(10)[:10]
    mensagem = b'G' + nome_cliente.encode('utf-8')
    tcp_sock.sendall(mensagem)

def mensagem_transacao(data):    # processa a mensagem de transação recebida do servidor
    num_transacao = int.from_bytes(data[0:2], 'big')
    num_cliente = int.from_bytes(data[2:4], 'big')
    tam_janela = int.from_bytes(data[4:8], 'big')
    bits_zero = data[8]
    tam_transacao = int.from_bytes(data[9:13], 'big')
    transacao = data[13:13+tam_transacao].decode('utf-8')
    print(f"Transação recebida: {transacao}, Bits: {bits_zero}, Janela: {tam_janela}")
    return num_transacao, num_cliente, tam_janela, bits_zero, transacao

def enviar_mensagem_submit(num_transacao, nonce):    # envia uma mensagem de submissão de nonce ao servidor
    mensagem = b'S' + num_transacao.to_bytes(2, 'big') + nonce.to_bytes(4, 'big')
    tcp_sock.sendall(mensagem)

def mensagem_validacao(data):    # processa mensagens de validação recebidas do servidor
    tipo_mensagem = data[0]
    num_transacao = int.from_bytes(data[1:3], 'big')
    if tipo_mensagem == ord('V'):
        print(f"Transação {num_transacao} validada com sucesso!")
    elif tipo_mensagem == ord('R'):
        print(f"Transação {num_transacao} rejeitada.")
    elif tipo_mensagem == ord('I'):
        print(f"Transação {num_transacao} foi validada por outro cliente.")
    elif tipo_mensagem == ord('Q'):
        print("Servidor encerrou a conexão...")
        sys.exit(0)

def servermsg():  # escuta mensagens do servidor com o protocolo e faz a verificação de nonce
    while True:
        try:
            data = tcp_sock.recv(1024)
            if not data:
                print("Conexão fechada pelo servidor.")
                break

            tipo_mensagem = data[0]
            if tipo_mensagem == ord('T'):
                num_transacao = int.from_bytes(data[1:3], 'big')
                num_cliente = int.from_bytes(data[3:5], 'big')
                tam_janela = int.from_bytes(data[5:9], 'big')
                bits_zero = data[9]
                tam_transacao = int.from_bytes(data[10:14], 'big')
                transacao = data[14:14+tam_transacao].decode('utf-8')
                print(f"Transação recebida: {transacao}, Bits: {bits_zero}, Janela: {tam_janela}")

                nonce_inicio = (num_cliente - 1) * tam_janela
                nonce_fim = nonce_inicio + tam_janela - 1
                print(f"Procurando nonce entre {nonce_inicio} e {nonce_fim}...")

                for nonce in range(nonce_inicio, nonce_fim + 1):
                    dados = nonce.to_bytes(4, 'big') + transacao.encode('utf-8')
                    hash_resultado = hashlib.sha256(dados).hexdigest()
                    hash_binario = bin(int(hash_resultado, 16))[2:].zfill(256)
                    if hash_binario.startswith("0" * bits_zero):
                        print(f"Nonce encontrado: {nonce}")
                        enviar_mensagem_submit(num_transacao, nonce)
                        break
            elif tipo_mensagem in [ord('V'), ord('R'), ord('I'), ord('Q')]:
                mensagem_validacao(data)
        except Exception as e:
            print(f"Erro ao receber mensagem do servidor: {e}")
            break

def startClient():
    # inicia o cliente e conecta ao servidor
    global tcp_sock
    try:
        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_sock.connect((HOST, PORT))
        print(f"Conectado ao servidor em {HOST}:{PORT}")
        enviar_mensagem_get("Cliente1")
    except Exception as e:
        print(f"Falha na conexão ao servidor: {e}")
        sys.exit(2)
    return tcp_sock

# Inicia o cliente
startClient()
thread_server = threading.Thread(target=servermsg)
thread_server.start()

try:
    thread_server.join()
except KeyboardInterrupt:
    print("Finalizando por Ctrl-C.")
    tcp_sock.close()
