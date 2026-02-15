# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                      Hotmart Course Downloader                                                      #
#                                                                                                                     #
#  Baseado no gist original de @juvenal: https://gist.github.com/juvenal/2d9a822325769d30c45c635fbf388c1b           #
#  Com melhorias para download de PDFs embutidos do Google Drive                                                     #
#                                                                                                                     #
#  NOTA: A API da Hotmart mudou (2026) e agora você precisa adicionar manualmente os subdomínios                     #
#        dos cursos no arquivo config_cursos.py                                                                      #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

# Requisitos:
# - FFMPEG instalado no sistema (adicionado às variáveis de ambiente)
# - Dependências Python: pip install -r requirements.txt
#   (m3u8, beautifulsoup4, youtube_dl, requests)
#
# Como usar:
# 1. Configure os subdomínios no config_cursos.py
# 2. Execute: python hotmark.py
# 3. Informe email e senha quando solicitado
#
# O que o script faz:
# - Baixa vídeos (Hotmart, Vimeo, YouTube)
# - Baixa anexos normais (PDFs, arquivos zip, etc)
# - Baixa PDFs embutidos do Google Drive (iframes)
# - Salva links de leitura complementar
# - Salva descrições das aulas
# - Retoma downloads interrompidos automaticamente
# - Organiza tudo em pastas por módulo/aula


import time
import datetime
import requests
import m3u8  # pip install m3u8
import re
import os
from bs4 import BeautifulSoup  # pip install beautifulsoup4
import youtube_dl  # pip install youtube_dl
import subprocess
import glob
import unicodedata
import re

def slugify(value, allow_unicode=False):
    """
    Taken from https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')


def extrair_google_drive_urls(html_content):
    """
    Extrai URLs do Google Drive de iframes no conteúdo HTML.
    Retorna uma lista de tuplas: (file_id, url_preview, url_download)
    """
    if not html_content:
        return []
    
    urls = []
    # Padrão para encontrar iframes com Google Drive
    pattern = r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)'
    matches = re.findall(pattern, html_content)
    
    for file_id in matches:
        preview_url = f"https://drive.google.com/file/d/{file_id}/preview"
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        urls.append((file_id, preview_url, download_url))
    
    return urls


def baixar_google_drive(file_id, download_url, output_path, first_folder):
    """
    Baixa um arquivo do Google Drive.
    Retorna True se o download foi bem-sucedido, False caso contrário.
    """
    try:
        loga(first_folder, "INFO", f"Iniciando download do Google Drive: {file_id}")
        
        # Cria uma sessão para manter cookies
        session = requests.Session()
        
        # Primeira tentativa: download direto
        response = session.get(download_url, stream=True)
        
        # Se o arquivo for grande, Google Drive mostra página de confirmação
        if 'confirm' in response.text or 'virus scan warning' in response.text.lower():
            # Procura pelo link de confirmação
            soup = BeautifulSoup(response.text, 'html.parser')
            for link in soup.find_all('a'):
                href = link.get('href', '')
                if 'export=download' in href and 'confirm' in href:
                    download_url = 'https://drive.google.com' + href
                    response = session.get(download_url, stream=True)
                    break
        
        # Salva o arquivo
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Verifica se o arquivo foi baixado corretamente
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                loga(first_folder, "INFO", f"Download concluído: {output_path} ({os.path.getsize(output_path)} bytes)")
                return True
            else:
                loga(first_folder, "ERRO", f"Arquivo vazio ou não criado: {output_path}")
                return False
        else:
            loga(first_folder, "ERRO", f"Falha no download do Google Drive: {response.status_code}")
            return False
            
    except Exception as e:
        loga(first_folder, "ERRO", f"Exceção ao baixar do Google Drive {file_id}: {str(e)}")
        return False

def loga(curso, status, msg):
    with open(curso + "/log.txt", "a", encoding="utf-8") as logz:
        logz.write(f"[{datetime.datetime.today().replace(microsecond=0)}] {status}: {msg}\n")


def autenticacao(**kwargs):
    if not os.path.exists('temp'):
        os.makedirs('temp')
    for f in glob.glob("temp/*"):
        os.remove(f)
    authMart = requests.session()
    authMart.headers[
        'user-agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.106 Safari/537.36'
    email = kwargs.get("email", None)
    if email is None:
        email = str(input("Qual o email de login?\n"))
    senha = kwargs.get("senha", None)
    if senha is None:
        senha = str(input("Qual a senha de login?\n"))
    data = {'username': email, 'password': senha, 'grant_type': 'password'}

    loga(".", "INFO", f"Tentando autenticar na hotmart com o payload {str(data)}")

    authSparkle = authMart.post('https://api.sparkleapp.com.br/oauth/token', data=data)

    if authSparkle.status_code == 200:
        loga(".", "INFO", f"Autenticação bem sucedida!")
    else:
        loga(".", "ERROR", f"Autenticação falhou. Código do erro:{authSparkle.status_code}")
        loga(".", "ERROR", f"{authSparkle.text}")
    authSparkle = authSparkle.json()

    try:
        params = {'token': authSparkle['access_token']}
    except KeyError:
        print("Email ou senha inválido, saindo")
        loga(".", "ERROR", f"Token não encontrado! User pode ter errado a senha.")
        loga(".", "ERROR", f"{authSparkle}")
        exit(13)
    authMart.headers.clear()
    authMart.headers[
        'user-agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.106 Safari/537.36'
    authMart.headers['authorization'] = 'Bearer ' + str(authSparkle['access_token'])
    return authMart, params


def listacursos(authMart, params):
    # Tenta pegar produtos do check_token
    check_token_response = authMart.get('https://api-sec-vlc.hotmart.com/security/oauth/check_token', params=params).json()
    
    # Salva a resposta completa para debug
    import json
    with open("api_response_debug.json", "w", encoding="utf-8") as f:
        json.dump(check_token_response, f, indent=2, ensure_ascii=False)
    
    loga(".", "DEBUG", f"Resposta do check_token salva em api_response_debug.json")
    
    produtos = check_token_response.get('resources', [])
    
    # Se não encontrou produtos via API, tenta carregar do arquivo de configuração
    if not produtos:
        loga(".", "WARN", f"Nenhum produto encontrado no check_token")
        print("\nAVISO: A API não retornou cursos automaticamente.")
        
        # Tenta importar do arquivo de configuração
        try:
            from config_cursos import CURSOS_SUBDOMINIOS
            if CURSOS_SUBDOMINIOS:
                print(f"\nEncontrados {len(CURSOS_SUBDOMINIOS)} curso(s) no arquivo config_cursos.py")
                for subdomain in CURSOS_SUBDOMINIOS:
                    produtos.append({
                        'resource': {
                            'subdomain': subdomain.strip(),
                            'status': 'ACTIVE'
                        },
                        'roles': ['STUDENT']
                    })
                loga(".", "INFO", f"Carregados {len(CURSOS_SUBDOMINIOS)} cursos do arquivo de configuração")
            else:
                print("\nAVISO: O arquivo config_cursos.py está vazio.")
        except ImportError:
            print("\nAVISO: Arquivo config_cursos.py não encontrado.")
        except Exception as e:
            loga(".", "ERROR", f"Erro ao carregar config_cursos.py: {e}")
            print(f"\nAVISO: Erro ao carregar configuração: {e}")
        
        # Se ainda não tem cursos, permite entrada manual
        if not produtos:
            print("\nPara encontrar o subdomínio do seu curso:")
            print("1. Acesse https://sun.hotmart.com/minhas-compras")
            print("2. Clique em 'Acessar' no curso desejado")
            print("3. Na URL você verá: https://hotmart.com/pt-br/club/SUBDOMAIN/...")
            print("4. O 'SUBDOMAIN' é o que você precisa informar")
            print("\nDica: Edite o arquivo 'config_cursos.py' para salvar os subdomínios permanentemente\n")
            
            # Permite adicionar múltiplos cursos manualmente
            subdominios_manuais = []
            while True:
                subdomain = input("Digite o subdomínio do curso (ou pressione Enter para finalizar): ").strip()
                if not subdomain:
                    if not subdominios_manuais:
                        print("AVISO: Nenhum curso adicionado. Finalizando...")
                        exit(0)
                    break
                subdominios_manuais.append(subdomain)
                print(f"Subdomínio '{subdomain}' adicionado\n")
            
            # Cria produtos com os subdomínios manuais
            for subdomain in subdominios_manuais:
                produtos.append({
                    'resource': {
                        'subdomain': subdomain,
                        'status': 'ACTIVE'
                    },
                    'roles': ['STUDENT']
                })
            
            loga(".", "INFO", f"Adicionados {len(subdominios_manuais)} cursos manualmente")

    loga(".", "INFO", f"Listando produtos da conta.")
    loga(".", "DEBUG", f"Total de produtos encontrados: {len(produtos)}")

    cursosValidos = []
    for idx, i in enumerate(produtos):
        try:
            loga(".", "DEBUG", f"Produto {idx + 1}: status={i.get('resource', {}).get('status')}, roles={i.get('roles')}")
            
            if i['resource']['status'] == "ACTIVE" and "STUDENT" in i['roles']:
                dominio = i['resource']['subdomain']
                loga(".", "DEBUG", f"Produto válido encontrado. Domínio: {dominio}")
                authMart.headers['origin'] = f'https://{dominio}.club.hotmart.com'
                authMart.headers['referer'] = f'https://{dominio}.club.hotmart.com'
                authMart.headers['club'] = dominio
                i["nome"] = re.sub(r'[<>:"/\\|?*]', '', authMart.get(
                    'https://api-club.hotmart.com/hot-club-api/rest/v3/membership?attach_token=false').json()[
                    'name']).strip()
                loga(".", "DEBUG", f"Nome do curso obtido: {i['nome']}")
                cursosValidos.append(i)
            else:
                loga(".", "DEBUG", f"Produto {idx + 1} não atende aos critérios (ACTIVE + STUDENT)")
        except KeyError as e:
            loga(".", "WARN", f"Produto presumido como inválido. Erro: {e}")
            loga(".", "WARN", f"{i}")
            continue
        except Exception as e:
            loga(".", "ERROR", f"Erro ao processar produto: {e}")
            loga(".", "ERROR", f"{i}")
            continue
    
    print(f"\n=== Cursos disponíveis ({len(cursosValidos)} encontrado(s)) ===")
    for i, curso in enumerate(cursosValidos, start=1):
        print(f"{i}. {curso['nome']}")
    opcao = int(input('Qual curso deseja baixar?\n')) - 1
    nmcurso = slugify(cursosValidos[opcao]['nome'])

    loga(".", "INFO", f"Iniciando download do curso {nmcurso}")
    loga(".", "INFO", f"{cursosValidos[opcao]}")
    first_folder = f'Cursos/{nmcurso}'
    if not os.path.exists(first_folder):
        os.makedirs(first_folder)
    dominio = cursosValidos[opcao]['resource']['subdomain']
    authMart.headers['origin'] = f'https://{dominio}.club.hotmart.com/'
    authMart.headers['referer'] = f'https://{dominio}.club.hotmart.com/'
    authMart.headers['club'] = dominio
    curso = authMart.get('https://api-club.hotmart.com/hot-club-api/rest/v3/navigation').json()
    estrutura = {}
    tempAula = []
    aulas = []
    tempAnexo = []
    tempLink = []
    x = 0

    loga(first_folder, "INFO", "Estrutura obtida com sucesso, criando dicionário")

    for modulo in curso['modules']:
        estrutura[modulo['moduleOrder']] = {re.sub(r'[<>:"/\\|?*]', '', modulo['name']).strip(): []}
        for i in modulo['pages']:
            x += 1
            print("Aulas contabilizadas:", x)
            aulas = [i['pageOrder'], re.sub(r'[<>:"/\\|?*]', '', i['name']).strip(), i['hash'], {'videos': []},
                     {'anexos': []}, {'links': []}]
            aula = authMart.get(f'https://api-club.hotmart.com/hot-club-api/rest/v3/page/{i["hash"]}').json()
            try:
                for video in aula['mediasSrc']:
                    tempAula = [re.sub(r'[<>:"/\\|?*]', '', video['mediaName']).strip(), video['mediaCode'],
                                video['mediaSrcUrl']]
                    aulas[3]['videos'].append(tempAula)
            except KeyError:
                pass
            try:
                for anexo in aula['attachments']:
                    tempAnexo = [anexo['fileMembershipId'], re.sub(r'[<>:"/\\|?*]', '', anexo['fileName']).strip()]
                    aulas[4]['anexos'].append(tempAnexo)
            except KeyError:
                pass
            try:
                for link in aula['complementaryReadings']:
                    tempLink = [re.sub(r'[<>:"/\\|?*]', '', link['articleName']).strip(), link['articleUrl']]
                    aulas[5]['links'].append(tempLink)
            except KeyError:
                pass
            estrutura[modulo['moduleOrder']][re.sub(r'[<>:"/\\|?*]', '', modulo['name']).strip()].append(aulas)

    # Dump do dict caso algo estranho ocorra a pessoa possa mandar, usar prettify.py para ver a monstruosidade
    with open(first_folder + '/debug.txt', 'a', encoding='utf-8') as debug:
        debug.write(str(curso['modules']) + '\n\n\n' + str(estrutura))

    loga(first_folder, "INFO", "Dicionário criado com sucesso, dumpado como debug.txt")
    loga(first_folder, "INFO", f"Total de aulas no curso {nmcurso} {str(x)}")

    for modulo in estrutura:
        for aulas in estrutura[modulo]:
            folder_path = f'{first_folder}/{slugify(str(modulo))}_{slugify(aulas)}'
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)

                loga(first_folder, "INFO", f"Criada a pasta do módulo {str(modulo)}.{aulas}")

            for aula in estrutura[modulo][aulas]:
                folder_path_class = f"{folder_path}/{slugify(str(aula[0]))}.{slugify(aula[1])}"
                print(f"Verificando a aula\n\t {folder_path_class}")
                if not os.path.exists(folder_path_class):
                    os.makedirs(folder_path_class)

                    loga(first_folder, "INFO", f"Criada a pasta da aula {slugify(str(aula[0]))}.{slugify(aula[1])}")

                try:
                    desct = authMart.get(f'https://api-club.hotmart.com/hot-club-api/rest/v3/page/{aula[2]}').json()[
                        'content']
                    with open(f"{folder_path_class}/descricao.html", 'w', encoding='utf-8') as dd:
                        dd.write(str(desct))
                        loga(first_folder, "INFO",
                             f"Descrição salva com sucesso, aula {str(aula[0])}.{aula[1]}")
                except KeyError:
                    print("Aula sem descrição/não textual")
                except:
                    print("Erro ao salvar descrição, churrasque-se")
                    loga(first_folder, "ERROR", f"Falha ao salvar a descrição da aula {str(aula[0])}. {aula[1]}")

                if not aula[3]['videos']:

                    loga(first_folder, "WARN",
                         "Aula não continha dicionário de videos, verificando por externos, verificar se é textual")

                    try:
                        pjson = BeautifulSoup(
                            authMart.get(f'https://api-club.hotmart.com/hot-club-api/rest/v3/page/{aula[2]}').json()[
                                'content'], features="html.parser")
                        viframe = pjson.findAll("iframe")
                        for x, i in enumerate(viframe, start=1):
                            if 'player.vimeo' in i.get("src"):
                                youtube_dl.utils.std_headers['Referer'] = f"https://{dominio}.club.hotmart.com/"

                                loga(first_folder, "INFO", f"Vídeo encontrado! {i.get('src')}")

                                if '?' in i.get("src"):
                                    linkV = i.get("src").split('?')[0]
                                else:
                                    linkV = i.get("src")
                                if linkV[-1] == "/":
                                    linkV = linkV.split("/")[-1]

                            elif 'vimeo.com' in i.get("src"):
                                youtube_dl.utils.std_headers['Referer'] = f"https://{dominio}.club.hotmart.com/"

                                loga(first_folder, "INFO", f"Vídeo encontrado! {i.get('src')}")

                                vimeoID = i.get("src").split('vimeo.com/')[1]
                                if "?" in vimeoID:
                                    vimeoID = vimeoID.split("?")[0]
                                linkV = "https://player.vimeo.com/video/" + vimeoID

                            elif "wistia.com" in i.get("src"):

                                loga(first_folder, "ERROR", f"WISTIA! Vídeo encontrado! {i.get('src')}")

                                # Método de download caiu, era pelo bin :( Ajuda noix Telegram: @katomaro
                                pass

                            elif "youtube.com" in i.get("src") or "youtu.be" in i.get("src"):

                                loga(first_folder, "INFO", f"Vídeo encontrado! {i.get('src')}")

                                linkV = i.get("src")
                            folder_path_class_video = f'{folder_path_class}/aula-{slugify(str(x))}.mp4'
                            if not os.path.isfile(folder_path_class_video):
                                print(f"Baixando aula externa\n\t {folder_path_class_video}")
                                ydl_opts = {"format": "best", 'outtmpl': folder_path_class_video}
                                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                                    ydl.download([linkV])
                                    loga(first_folder, "INFO", f"Vídeo externo baixado com sucesso.")
                            else:
                                print("Aula já presente, pulando")
                                loga(first_folder, "INFO", "Aulá já presente! Pulada")

                    except:

                        loga(first_folder, "WARN",
                             "Plataforma não retornou vídeos, verificar se é postagem (aula textual)")

                        pass

                else:  # 0 nome, 1 id, 2 link
                    for x, i in enumerate(aula[3]['videos'], start=1):
                        folder_path_class_video = f'{folder_path_class}/aula-{slugify(str(x))}.mp4'
                        if not os.path.isfile(folder_path_class_video):
                            print(f"Tentando baixar aula da hotmart\n\t {folder_path_class_video}")
                            loga(first_folder, "INFO", f"Tentando baixar a aula {str(x)} ({aula[1]})")

                            mediaUrl = i[2]
                            authMart.get(mediaUrl)
                            videoHash = i[1]
                            teste = authMart.get(f"https://contentplayer.hotmart.com/video/{videoHash}/hls/master.m3u8")
                            masterPlaylist = m3u8.loads(teste.text)
                            res = []
                            for playlist in masterPlaylist.playlists:
                                res.append(playlist.stream_info.resolution)
                            res.sort(reverse=True)
                            highestQual = "720"  # TODO: Check the lowest quality available?
                            for playlist in masterPlaylist.playlists:
                                if playlist.stream_info.resolution == res[0]:
                                    highestQual = playlist.uri
                            print(f"highestQual: {highestQual}")

                            highqual = authMart.get(
                                f"https://contentplayer.hotmart.com/video/{videoHash}/hls/{highestQual}")

                            loga(first_folder, "INFO",
                                 f"Melhor qualidade encontrada {str(highestQual).split('/')[0]}p")

                            with open('temp/dump.m3u8', 'w') as dump:
                                dump.write(highqual.text)
                            targetm3u8 = m3u8.loads(highqual.text)
                            key = None
                            for segment in targetm3u8.segments:
                                key = segment.key.uri
                                uri = segment.uri
                                frag = authMart.get(
                                    f"https://contentplayer.hotmart.com/video/{videoHash}/hls/{highestQual.split('/')[0]}/{uri}")
                                with open("temp/" + uri, 'wb') as sfrag:
                                    sfrag.write(frag.content)
                            print()
                            print("Segmentos baixados")
                            fragkey = authMart.get(
                                f"https://contentplayer.hotmart.com/video/{videoHash}/hls/{highestQual.split('/')[0]}/{key}")
                            with open("temp/" + str(key), 'wb') as skey:
                                skey.write(fragkey.content)
                            print("Chave de decodificação baixada, concatenando...")
                            ffmpegcmd = f'ffmpeg -hide_banner -loglevel error -allowed_extensions ALL -i temp/dump.m3u8 -preset ultrafast  "{folder_path_class_video}"'

                            loga(first_folder, "INFO", "Iniciando o FFMPEG")
                            try:
                                subprocess.run(ffmpegcmd)
                                print("Download da aula concluído, limpado pasta temporária...")
                                loga(first_folder, "INFO", "FFMPEG concluído, aula baixada.")
                            except Exception as e:
                                loga(first_folder, "INFO", f"Erro ao rodar FFMPEG: {e}")
                                print(e)

                            time.sleep(1)
                            for f in glob.glob("temp/*"):
                                os.remove(f)

                            loga(first_folder, "INFO", "Pasta temporária limpa")
                        else:
                            print("Aula já presente, pulando")
                            loga(first_folder, "INFO", "Aulá já presente, pulada")

                if aula[4]['anexos']:  # 0 id 1 nome
                    print(f"\n{len(aula[4]['anexos'])} anexo(s) encontrado(s) para a aula: {aula[1]}")
                    folder_path_class_attach = f"{folder_path}/{slugify(str(aula[0]))}.{slugify(aula[1])}/Materiais"
                    if not os.path.exists(folder_path_class_attach):
                        os.makedirs(folder_path_class_attach)
                        loga(first_folder, "INFO",
                             f"Pasta de anexos criada na aula {str(aula[0])}. {aula[1]}")
                    
                    anexos_baixados = 0
                    anexos_pulados = 0
                    anexos_falhos = 0
                    
                    for idx, i in enumerate(aula[4]['anexos'], 1):
                        anexo_id = i[0]
                        anexo_nome = i[1]
                        folder_path_class_attach_file = f"{folder_path_class_attach}/{anexo_nome}"
                        
                        print(f"  [{idx}/{len(aula[4]['anexos'])}] {anexo_nome}")
                        
                        if os.path.isfile(folder_path_class_attach_file):
                            file_size = os.path.getsize(folder_path_class_attach_file)
                            if file_size > 0:
                                print(f"      [OK] Já existe ({file_size} bytes) - pulando")
                                loga(first_folder, "INFO", f"Anexo já existente: {anexo_nome} ({file_size} bytes)")
                                anexos_pulados += 1
                                continue
                            else:
                                print(f"      [AVISO] Arquivo existe mas está vazio - rebaixando")
                                loga(first_folder, "WARN", f"Anexo vazio detectado, rebaixando: {anexo_nome}")
                                os.remove(folder_path_class_attach_file)
                        
                        # Tenta baixar com retry
                        max_tentativas = 3
                        sucesso = False
                        
                        for tentativa in range(1, max_tentativas + 1):
                            try:
                                if tentativa > 1:
                                    print(f"      [RETRY] Tentativa {tentativa}/{max_tentativas}...")
                                    time.sleep(2)  # Aguarda antes de retry
                                
                                loga(first_folder, "INFO", f"Baixando anexo {anexo_nome} (tentativa {tentativa})")
                                
                                # Tenta obter URL de download
                                response = authMart.get(
                                    f'https://api-club.hotmart.com/hot-club-api/rest/v3/attachment/{anexo_id}/download',
                                    timeout=30
                                )
                                
                                if response.status_code != 200:
                                    raise Exception(f"Erro HTTP {response.status_code}: {response.text[:100]}")
                                
                                anexo_info = response.json()
                                
                                # Tenta baixar via directDownloadUrl
                                if 'directDownloadUrl' in anexo_info:
                                    print(f"      [DOWNLOAD] Baixando via directDownloadUrl...")
                                    anexo = requests.get(anexo_info['directDownloadUrl'], timeout=60)
                                    
                                    if anexo.status_code != 200:
                                        raise Exception(f"Erro ao baixar: HTTP {anexo.status_code}")
                                
                                # Fallback para lambdaUrl
                                elif 'lambdaUrl' in anexo_info:
                                    print(f"      [DOWNLOAD] Baixando via lambdaUrl...")
                                    vrum = requests.session()
                                    vrum.headers.update(authMart.headers)
                                    vrum.headers['token'] = anexo_info.get('token', '')
                                    
                                    lambda_response = vrum.get(anexo_info['lambdaUrl'], timeout=30)
                                    download_url = lambda_response.text
                                    anexo = requests.get(download_url, timeout=60)
                                    del vrum
                                    
                                    if anexo.status_code != 200:
                                        raise Exception(f"Erro ao baixar via lambda: HTTP {anexo.status_code}")
                                else:
                                    raise Exception("Nenhuma URL de download encontrada na resposta da API")
                                
                                # Valida o conteúdo
                                if not anexo.content or len(anexo.content) == 0:
                                    raise Exception("Conteúdo vazio recebido")
                                
                                # Salva o arquivo
                                with open(folder_path_class_attach_file, 'wb') as ann:
                                    ann.write(anexo.content)
                                
                                # Verifica se foi salvo corretamente
                                if not os.path.exists(folder_path_class_attach_file):
                                    raise Exception("Arquivo não foi salvo")
                                
                                file_size = os.path.getsize(folder_path_class_attach_file)
                                if file_size == 0:
                                    raise Exception("Arquivo salvo está vazio")
                                
                                # Sucesso!
                                print(f"      [OK] Baixado com sucesso ({file_size} bytes)")
                                loga(first_folder, "INFO", f"Anexo baixado: {anexo_nome} ({file_size} bytes)")
                                anexos_baixados += 1
                                sucesso = True
                                break
                                
                            except Exception as e:
                                erro_msg = str(e)
                                loga(first_folder, "ERROR", f"Erro ao baixar anexo {anexo_nome} (tentativa {tentativa}): {erro_msg}")
                                
                                if tentativa == max_tentativas:
                                    print(f"      [ERRO] FALHA após {max_tentativas} tentativas: {erro_msg}")
                                    anexos_falhos += 1
                                    
                                    # Remove arquivo parcial se existir
                                    if os.path.exists(folder_path_class_attach_file):
                                        try:
                                            os.remove(folder_path_class_attach_file)
                                        except:
                                            pass
                                else:
                                    print(f"      [AVISO] Erro: {erro_msg}")
                        
                        # Pequena pausa entre downloads
                        if sucesso:
                            time.sleep(0.5)
                    
                    # Resumo dos anexos
                    print(f"\n  [RESUMO] Anexos:")
                    print(f"     Baixados: {anexos_baixados}")
                    print(f"     Pulados: {anexos_pulados}")
                    if anexos_falhos > 0:
                        print(f"     Falhas: {anexos_falhos}")
                    print()
                    
                    loga(first_folder, "INFO", f"Anexos processados - Baixados: {anexos_baixados}, Pulados: {anexos_pulados}, Falhas: {anexos_falhos}")

                # Processar PDFs embutidos no campo 'content' (Google Drive iframes)
                try:
                    aula_completa = authMart.get(f'https://api-club.hotmart.com/hot-club-api/rest/v3/page/{aula[2]}').json()
                    content_html = aula_completa.get('content', '')
                    
                    if content_html:
                        google_drive_files = extrair_google_drive_urls(content_html)
                        
                        if google_drive_files:
                            print(f"\n{len(google_drive_files)} arquivo(s) do Google Drive encontrado(s) no conteúdo")
                            
                            folder_path_class_attach = f"{folder_path}/{slugify(str(aula[0]))}.{slugify(aula[1])}/Materiais"
                            if not os.path.exists(folder_path_class_attach):
                                os.makedirs(folder_path_class_attach)
                                loga(first_folder, "INFO", f"Pasta de materiais criada para Google Drive files")
                            
                            gdrive_baixados = 0
                            gdrive_pulados = 0
                            gdrive_falhos = 0
                            
                            for idx, (file_id, preview_url, download_url) in enumerate(google_drive_files, 1):
                                # Nome baseado no file_id já que não temos nome do arquivo
                                file_name = f"gdrive_{file_id}.pdf"
                                output_path = f"{folder_path_class_attach}/{file_name}"
                                
                                print(f"  [{idx}/{len(google_drive_files)}] {file_name}")
                                
                                # Verifica se já existe
                                if os.path.isfile(output_path):
                                    file_size = os.path.getsize(output_path)
                                    if file_size > 0:
                                        print(f"      [OK] Já existe ({file_size} bytes) - pulando")
                                        loga(first_folder, "INFO", f"Google Drive file já existente: {file_name}")
                                        gdrive_pulados += 1
                                        continue
                                    else:
                                        print(f"      [AVISO] Arquivo existe mas está vazio - rebaixando")
                                        os.remove(output_path)
                                
                                # Tenta baixar
                                print(f"      [DOWNLOAD] Baixando do Google Drive...")
                                sucesso = baixar_google_drive(file_id, download_url, output_path, first_folder)
                                
                                if sucesso:
                                    print(f"      [OK] Baixado com sucesso")
                                    gdrive_baixados += 1
                                else:
                                    print(f"      [ERRO] Falha no download")
                                    gdrive_falhos += 1
                                
                                time.sleep(1)  # Pausa entre downloads
                            
                            # Resumo
                            print(f"\n  [RESUMO] Arquivos do Google Drive:")
                            print(f"     Baixados: {gdrive_baixados}")
                            print(f"     Pulados: {gdrive_pulados}")
                            if gdrive_falhos > 0:
                                print(f"     Falhas: {gdrive_falhos}")
                            print()
                            
                            loga(first_folder, "INFO", f"Google Drive files - Baixados: {gdrive_baixados}, Pulados: {gdrive_pulados}, Falhas: {gdrive_falhos}")
                
                except Exception as e:
                    loga(first_folder, "ERROR", f"Erro ao processar conteúdo Google Drive: {str(e)}")

                if aula[5]['links']:  # 0 nome 1 url
                    folder_path_class_attach = f"{folder_path}/{slugify(str(aula[0]))}.{slugify(aula[1])}/Materiais"
                    print(f"Salvando links encontrados para a aula\n\t {folder_path_class_attach}")
                    loga(first_folder, "INFO", f"Links detectados para a aula {str(aula[0])}{aula[1]}")
                    folder_path_class_links = f"{folder_path_class_attach}/links.txt"
                    with open(folder_path_class_links, "a", encoding="utf-8") as linkz:
                        for i in aula[5]['links']:
                            linkz.write(f"{i[0]}: {i[1]}\n")
                    loga(first_folder, "INFO", "Links salvos")


# login = {"email": "EMAIL@EMAIL", "senha": "SENHA"}
login = {
    "Info": "Pode colocar o email/senha ali em cima e apagar esse dicionário para deixar os dados salvos no script",
    "autor": "Telegram: @katomaro"}

listacursos(*autenticacao(**login))
