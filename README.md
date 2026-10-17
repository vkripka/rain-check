# 🌧️ Rain Check — Vai Chover Amanhã? (PWA iOS + Web Push às 21h)

Aplicativo meteorológico desenhado sob medida para **iPhone (iOS 16.4+)** que responde de imediato se **vai chover amanhã ou não**, detalha as **próximas 24 horas** e os **4 turnos do dia seguinte** (Madrugada, Manhã, Tarde e Noite), e envia uma **notificação Push automática todo dia às 21:00** com a previsão atualizada em background.

---

## 🚀 Como testar agora no Computador
O servidor já está configurado e rodando em:
👉 **[http://localhost:5000](http://localhost:5000)**

Para iniciar novamente no futuro com 2 cliques, basta abrir o arquivo [`iniciar_rain_check.bat`](./iniciar_rain_check.bat).

---

## 📱 Como instalar no seu iPhone e receber a Notificação às 21h (24/7)

Como o iPhone exige **HTTPS (`https://`)** para liberar o **GPS** e as **Notificações Web Push** da Apple (APNs), e para que a notificação das **21:00** funcione todos os dias **mesmo com o seu computador desligado**, você tem duas opções gratuitas:

### Opção A: Hospedar 24h por dia Gratuitamente no Render.com (Recomendado para uso diário definitivo)
1. Suba esta pasta para um repositório no seu **GitHub**.
2. Acesse [render.com](https://render.com) (gratuito), clique em **New + → Blueprint** (ou **Web Service**) e conecte o repositório (o arquivo [`render.yaml`](./render.yaml) já configura tudo automaticamente).
3. Você receberá um link permanente `https://rain-check-pwa.onrender.com`.
4. *(Dica para plano gratuito do Render)*: Cadastre a URL `https://SEU-APP.onrender.com/api/cron/trigger` gratuitamente no site [cron-job.org](https://cron-job.org) programado para **todos os dias às 21:00** (fuso `America/Sao_Paulo`). Assim, às 21:00 em ponto ele acorda o servidor, consulta a meteorologia em tempo real e envia o Push para o seu iPhone!

### Opção B: Testar imediatamente no seu iPhone usando seu PC Windows (Túnel HTTPS instantâneo)
Abra o PowerShell na pasta do projeto e rode:
```powershell
ssh -R 80:localhost:5000 nokey@localhost.run
```
Ele mostrará no final um link `https://xxxx.lhr.life` (com QR Code).

---

## 📲 Passo a Passo no iPhone (Safari)
1. Abra o link `https://...` do seu **Rain Check** no **Safari** do iPhone.
2. Toque no botão **Compartilhar** (`⎋` na barra inferior do Safari).
3. Role para baixo e toque em **"Adicionar à Tela de Início"**.
4. Abra o aplicativo **Rain Check** pelo novo ícone na tela inicial do seu iPhone.
5. Permita o acesso à localização GPS e ative a chave **"Alerta Diário às 21h"**.
6. Toque em **"Disparar Teste Agora"** para receber imediatamente a notificação na tela de bloqueio do seu iPhone!
