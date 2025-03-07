import socket
import threading
import time
import hashlib
import ssl
import struct
import requests

HOST = "localhost"
PORT = 31471  
WINDOW_SIZE = 100000
TIMEOUT = 60  

BOT_TOKEN = "8022479701:AAG0FL1L59S3WBtYRrVmiWu4aVNaJIdXeMc"  
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"  
TELEGRAM_CHAT_IDS = []

transacoes_pendentes = []
transacoes_validadas = []
clientes = {} 
lock = threading.Lock()

def validar_nonce(transacao, nonce, bits): # verificação do nonce
    dados = nonce.to_bytes(4, 'big') + transacao.encode("utf-8")
    hash_resultado = hashlib.sha256(dados).hexdigest()
    hash_binario = bin(int(hash_resultado, 16))[2:].zfill(256)
    return hash_binario.startswith("0" * bits)

def aceitar_clientes():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((HOST, PORT))
        servidor.listen()
        print(f"Servidor: Aguardando conexões na porta {PORT}...")
        
        while True:
            conn, addr = servidor.accept()
            with lock:
                clientes[addr] = None
            print(f"Novo cliente conectado  {addr}")
            threading.Thread(target=gerenciar_cliente, args=(conn, addr)).start()

def gerenciar_cliente(conn, addr): #faz a verificação do protocolo, verifica trans pendente 
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break

            tipo_mensagem = data[0]
            if tipo_mensagem == ord('G'):
                nome_cliente = data[1:11].decode('utf-8').strip()
                with lock:
                    if transacoes_pendentes:
                        transacao, bits, clientes_validando = transacoes_pendentes[0]
                        nonce_inicio = clientes_validando * WINDOW_SIZE
                        clientes_validando += 1
                        transacoes_pendentes[0] = (transacao, bits, clientes_validando)
                        clientes[addr] = (transacao, nonce_inicio, nonce_inicio + WINDOW_SIZE - 1)
                        resposta = b'T' + struct.pack('>H', 1) + struct.pack('>H', clientes_validando) + struct.pack('>I', WINDOW_SIZE) + struct.pack('>B', bits) + struct.pack('>I', len(transacao)) + transacao.encode('utf-8')
                    else:
                        resposta = b'W'
                conn.sendall(resposta)
            elif tipo_mensagem == ord('S'):
                num_transacao = int.from_bytes(data[1:3], 'big')
                nonce = int.from_bytes(data[3:7], 'big')
                with lock:
                    transacao, bits, _ = transacoes_pendentes[0]
                    if validar_nonce(transacao, nonce, bits):
                        transacoes_validadas.append((transacao, bits, nonce, addr))
                        transacoes_pendentes.pop(0)
                        conn.sendall(b'V' + num_transacao.to_bytes(2, 'big'))
                        for cliente in clientes:
                            if cliente != addr:
                                conn.sendall(b'I' + num_transacao.to_bytes(2, 'big'))
                    else:
                        conn.sendall(b'R' + num_transacao.to_bytes(2, 'big'))
    except ConnectionResetError:
        # Captura o erro específico de conexão resetada (WinError 10054)
        print(f"Desconectado {addr} saiu.")
    except Exception as e:
        print(f"Erro Conexão perdida com {addr}: {e}")
    finally:
        conn.close()
        with lock:
            clientes.pop(addr, None)

def exibir_menu():
    print("/newtrans /validtrans /pendtrans /clients sair ")

def interface_usuario():
    while True:
        exibir_menu()
        comando = input("Digite um comando: ")
        if comando == "/newtrans":
            transacao = input("Digite a transação: ")
            bits = int(input("Digite a quantidade de bits zero: "))
            with lock:
                transacoes_pendentes.append((transacao, bits, 0))
                print(f"Nova transação {transacao} adicionada com {bits} bits zero.")
        elif comando == "/validtrans":
            with lock:
                if transacoes_validadas:
                    for t in transacoes_validadas:
                        print(f"Transação: {t[0]}, Bits: {t[1]}, Nonce: {t[2]}, Cliente: {t[3]}")
                else:
                    print("Nenhuma transação validada ainda.")
        elif comando == "/pendtrans":
            with lock:
                if transacoes_pendentes:
                    for t in transacoes_pendentes:
                        print(f"Transação: {t[0]}, Bits: {t[1]}, Clientes validando: {t[2]}")
                else:
                    print("Nenhuma transação pendente.")
        elif comando == "/clients":
            with lock:
                if clientes:
                    for addr, t in clientes.items():
                        if t:
                            print(f"Cliente {addr} validando {t[0]} ({t[1]}-{t[2]})")
                        else:
                            print(f"Cliente {addr} conectado, mas sem transação atribuída.")
                else:
                    print("Nenhum cliente conectado.")
        elif comando.lower() == "sair":
            print("Encerrando o servidor...")
            break
        else:
            print("Comando não reconhecido. Tente novamente.")

def enviar_mensagem_telegram(chat_id, mensagem):
    url = f"{TELEGRAM_API_URL}sendMessage"
    params = {
        "chat_id": chat_id,
        "text": mensagem
    }
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            print(f"Telegram: Mensagem enviada para o chat {chat_id}.")
        else:
            print(f"Telegram: Erro ao enviar mensagem: {response.text}")
    except Exception as e:
        print(f"Telegram: Erro na comunicação com a API: {e}")

def processar_comando_telegram(comando, chat_id):
    # processa comandos recebidos pelo Telegram
    if comando == "/validtrans":
        with lock:
            if transacoes_validadas:
                mensagem = "Transações validadas:\n"
                for t in transacoes_validadas:
                    mensagem += f"Transação: {t[0]}, Bits: {t[1]}, Nonce: {t[2]}, Cliente: {t[3]}\n"
            else:
                mensagem = "Nenhuma transação validada ainda."
        enviar_mensagem_telegram(chat_id, mensagem)
    elif comando == "/pendtrans":
        with lock:
            if transacoes_pendentes:
                mensagem = "Transações pendentes:\n"
                for t in transacoes_pendentes:
                    mensagem += f"Transação: {t[0]}, Bits: {t[1]}, Clientes validando: {t[2]}\n"
            else:
                mensagem = "Nenhuma transação pendente."
        enviar_mensagem_telegram(chat_id, mensagem)
    elif comando == "/clients":
        with lock:
            if clientes:
                mensagem = "Clientes conectados:\n"
                for addr, t in clientes.items():
                    if t:
                        mensagem += f"Cliente {addr} validando {t[0]} ({t[1]}-{t[2]})\n"
                    else:
                        mensagem += f"Cliente {addr} conectado, mas sem transação atribuída.\n"
            else:
                mensagem = "Nenhum cliente conectado."
        enviar_mensagem_telegram(chat_id, mensagem)
    else:
        enviar_mensagem_telegram(chat_id, "Comando não reconhecido. Use /validtrans, /pendtrans ou /clients.")

def monitorar_telegram():
    offset = 0
    while True:
        url = f"{TELEGRAM_API_URL}getUpdates"
        params = {"offset": offset, "timeout": 30}
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                updates = response.json().get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1
                    chat_id = update["message"]["chat"]["id"]
                    texto = update["message"]["text"]
                    processar_comando_telegram(texto, chat_id)
        except Exception as e:
            print(f"Telegram: Erro ao monitorar mensagens: {e}")
        time.sleep(1)

t1 = threading.Thread(target=aceitar_clientes)  
t2 = threading.Thread(target=interface_usuario)  
t3 = threading.Thread(target=monitorar_telegram)  
t1.start()  
t2.start()  
t3.start()  
t1.join()  
t2.join()  
t3.join()
