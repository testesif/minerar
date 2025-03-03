import socket
import threading
import time
import hashlib

# Configurações do servidor
HOST = 'localhost'
PORTA = 31471

# Função para solicitar uma transação ao servidor
def solicitar_transacao(conexao):
    # Envia a solicitação de transação (tipo 1)
    conexao.sendall((1).to_bytes(2, 'big'))
    
    # Recebe a resposta do servidor
    resposta = conexao.recv(1024)
    if resposta == b"SEM_TRANSACOES":
        print("Não há transações disponíveis no momento.")
        return None, None, None, None, None
    
    # Decodifica a resposta
    try:
        tamanho_transacao = int.from_bytes(resposta[:2], 'big')
        transacao = resposta[2:2 + tamanho_transacao].decode('utf-8')
        bits_zero = int.from_bytes(resposta[2 + tamanho_transacao:6 + tamanho_transacao], 'big')
        clientes_validando = int.from_bytes(resposta[6 + tamanho_transacao:10 + tamanho_transacao], 'big')
        inicio_janela = int.from_bytes(resposta[10 + tamanho_transacao:18 + tamanho_transacao], 'big')
        fim_janela = int.from_bytes(resposta[18 + tamanho_transacao:26 + tamanho_transacao], 'big')
        
        # Verifica se a transação e a janela são válidas
        if not transacao or inicio_janela >= fim_janela:
            print("Transação ou janela de validação inválida recebida do servidor.")
            return None, None, None, None, None
        
        return transacao, bits_zero, clientes_validando, inicio_janela, fim_janela
    except Exception as e:
        print(f"Erro ao decodificar a resposta do servidor: {e}")
        return None, None, None, None, None

# Função para calcular o hash SHA256
def calcular_hash(nonce, transacao):
    dados = nonce + transacao.encode('utf-8')
    return hashlib.sha256(dados).hexdigest()

# Função para minerar a transação
def minerar_transacao(conexao, transacao, bits_zero, inicio_janela, fim_janela):
    if not transacao or inicio_janela >= fim_janela:
        print("Transação ou janela de validação inválida. Ignorando mineração.")
        return
    
    print(f"Iniciando mineração para a transação: {transacao}")
    print(f"Janela de validação: {inicio_janela} a {fim_janela}")
    
    for nonce in range(inicio_janela, fim_janela + 1):
        # Verifica se o servidor enviou uma notificação para parar a mineração
        conexao.settimeout(0.1)  # Define um timeout para verificar notificações
        try:
            notificacao = conexao.recv(1024)
            if notificacao == b"PARAR_MINERACAO":
                print("Recebida notificação para parar a mineração.")
                return
        except socket.timeout:
            pass  # Nenhuma notificação recebida, continue a mineração
        
        nonce_bytes = nonce.to_bytes(4, 'big')
        hash_resultado = calcular_hash(nonce_bytes, transacao)
        
        # Verifica se o hash começa com a quantidade de bits zero esperada
        if hash_resultado.startswith('0' * bits_zero):
            print(f"Nonce encontrado: {nonce}")
            # Envia o nonce ao servidor (tipo 2)
            conexao.sendall((2).to_bytes(2, 'big') + nonce_bytes)
            # Recebe a confirmação do servidor
            confirmacao = conexao.recv(1024)
            if confirmacao == b"VALIDACAO_SUCESSO":
                print("Nonce validado com sucesso!")
            else:
                print("Falha ao validar o nonce.")
            return  # Encerra a mineração após encontrar um nonce válido
    else:
        print("Nonce não encontrado na janela de validação.")

# Função para manter a conexão ativa
def manter_conexao_ativa(conexao):
    while True:
        time.sleep(50)  # Envia uma solicitação a cada 50 segundos
        try:
            conexao.sendall((1).to_bytes(2, 'big'))
        except:
            print("Erro ao manter a conexão ativa.")
            break

# Função principal do cliente
def main():
    try:
        # Conecta ao servidor
        conexao = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conexao.connect((HOST, PORTA))
        print(f"Conectado ao servidor {HOST}:{PORTA}")
        
        # Inicia a thread para manter a conexão ativa
        threading.Thread(target=manter_conexao_ativa, args=(conexao,), daemon=True).start()
        
        while True:
            # Solicita uma transação ao servidor
            transacao, bits_zero, clientes_validando, inicio_janela, fim_janela = solicitar_transacao(conexao)
            if transacao is None:
                time.sleep(10)  # Aguarda 10 segundos antes de tentar novamente
                continue
            
            # Inicia o processo de mineração
            minerar_transacao(conexao, transacao, bits_zero, inicio_janela, fim_janela)
            
    except Exception as e:
        print(f"Erro no cliente: {e}")
    finally:
        conexao.close()
        print("Conexão com o servidor fechada.")

if __name__ == "__main__":
    main()
