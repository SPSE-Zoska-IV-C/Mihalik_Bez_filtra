# Nastavenie Google OAuth prihlasovania

## Krok 1: Vytvorenie Google Cloud projektu a OAuth credentials

### 1.1. Choď na Google Cloud Console
1. Otvor: https://console.cloud.google.com/
2. Prihlás sa s Google účtom

### 1.2. Vytvor nový projekt
1. Klikni na dropdown "Select a project" v hornej lište
2. Klikni na "NEW PROJECT"
3. **Project name**: `Bez Filtra` (alebo akýkoľvek názov)
4. Klikni "CREATE"
5. Počkaj, kým sa projekt vytvorí (môže to trvať pár sekúnd)
6. Vyber nový projekt z dropdownu

### 1.3. Povol OAuth Consent Screen
1. V ľavom menu choď na **"APIs & Services"** → **"OAuth consent screen"**
2. Vyber **"External"** (pre testovanie) a klikni "CREATE"
3. Vyplň formulár:
   - **App name**: `Bez Filtra` (alebo tvoj názov)
   - **User support email**: Tvoj email
   - **Developer contact information**: Tvoj email
4. Klikni "SAVE AND CONTINUE"
5. Na stránke "Scopes" klikni "SAVE AND CONTINUE" (bez zmien)
6. Na stránke "Test users" (ak je External):
   - Klikni "ADD USERS"
   - Pridaj svoj email
   - Klikni "ADD"
   - Klikni "SAVE AND CONTINUE"
7. Na stránke "Summary" klikni "BACK TO DASHBOARD"

### 1.4. Vytvor OAuth 2.0 Client ID
1. V ľavom menu choď na **"APIs & Services"** → **"Credentials"**
2. Klikni na **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**
3. **Application type**: Vyber **"Web application"**
4. **Name**: `Bez Filtra Web Client` (alebo akýkoľvek názov)
5. **Authorized JavaScript origins**:
   - Pridaj: `http://localhost:5000` (pre lokálne testovanie)
   - Ak máš produkčnú URL, pridaj aj ju
6. **Authorized redirect URIs**:
   - Pridaj: `http://localhost:5000/callback/google`
   - Ak máš produkčnú URL, pridaj: `https://tvoja-url.com/callback/google`
7. Klikni **"CREATE"**
8. **DÔLEŽITÉ**: Zobrazí sa dialóg s **Client ID** a **Client Secret**
   - **Skopíruj oba** - Client Secret sa zobrazí len raz!

## Krok 2: Nastavenie v projekte

### 2.1. Nastav Environment Variables

**Windows PowerShell:**
```powershell
$env:GOOGLE_CLIENT_ID="tvoje-client-id.apps.googleusercontent.com"
$env:GOOGLE_CLIENT_SECRET="tvoje-client-secret"
```

**Windows CMD:**
```cmd
set GOOGLE_CLIENT_ID=tvoje-client-id.apps.googleusercontent.com
set GOOGLE_CLIENT_SECRET=tvoje-client-secret
```

**Linux/Mac:**
```bash
export GOOGLE_CLIENT_ID="tvoje-client-id.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="tvoje-client-secret"
```

### 2.2. Trvalé nastavenie (Windows)
1. Stlač `Win + R`
2. Napíš `sysdm.cpl` a stlač Enter
3. Klikni na "Environment Variables"
4. V "User variables" klikni "New" pre každú premennú:
   - **GOOGLE_CLIENT_ID** = tvoje Client ID
   - **GOOGLE_CLIENT_SECRET** = tvoje Client Secret
5. Klikni OK a reštartuj terminál/IDE

## Krok 3: Nainštaluj závislosti

```bash
pip install -r requirements.txt
```

## Krok 4: Vytvor databázovú migráciu (ak potrebuješ)

Ak už máš používateľov v databáze, možno budeš potrebovať migráciu pre nové stĺpce:
```bash
flask db migrate -m "Add Google OAuth support"
flask db upgrade
```

Alebo môžeš pridať stĺpce manuálne v databáze:
```sql
ALTER TABLE user ADD COLUMN google_id VARCHAR(255);
ALTER TABLE user ADD COLUMN password_hash VARCHAR(128) NULL;
```

## Krok 5: Reštartuj aplikáciu

1. Zastav Flask aplikáciu (Ctrl+C)
2. Spusti znova: `python app.py`
3. Choď na `/register` alebo `/login`
4. Mala by sa zobraziť tlačidlo **"Continue with Google"**

## Overenie

1. Klikni na "Continue with Google"
2. Mala by sa otvoriť Google prihlasovacia stránka
3. Prihlás sa s Google účtom
4. Súhlas s oprávneniami
5. Mala by sa zobraziť správa "Logged in successfully with Google!"
6. Budeš prihlásený a presmerovaný na hlavnú stránku

## Riešenie problémov

### "Google login is not configured"
- Skontroluj, či sú nastavené environment variables
- Reštartuj aplikáciu po nastavení

### "redirect_uri_mismatch"
- Skontroluj, či je redirect URI v Google Console presne: `http://localhost:5000/callback/google`
- Musí byť presne rovnaké (vrátane http/https, portu, cesty)

### "access_denied"
- Skontroluj, či je tvoj email v "Test users" (ak používaš External app)
- Alebo publikuj app (pre produkciu)

### Databázové chyby
- Skontroluj, či máš stĺpce `google_id` a `password_hash` (nullable) v User tabuľke
- Vytvor migráciu alebo pridaj manuálne

## Bezpečnostné poznámky

- **NIKDY** necommitni Client Secret do Gitu!
- Používaj environment variables
- Pre produkciu použij HTTPS
- Aktualizuj redirect URIs v Google Console pre produkčnú URL



