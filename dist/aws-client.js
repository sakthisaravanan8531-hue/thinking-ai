/* Public configuration only. Never put Gemini keys or AWS credentials here.
   Cognito JWTs remain in memory; re-login after refresh. */
export function thinkingAws({ apiUrl, region, clientId }) {
  let token = null, challenge = null;
  const cognitoUrl = `https://cognito-idp.${region}.amazonaws.com/`;
  async function cognito(action, data) {
    const r = await fetch(cognitoUrl, {method: 'POST', headers: {
      'Content-Type': 'application/x-amz-json-1.1',
      'X-Amz-Target': `AWSCognitoIdentityProviderService.${action}`}, body: JSON.stringify(data)});
    const result = await r.json();
    if (!r.ok) { const error = new Error(result.message || 'Account request failed'); error.code = String(result.__type || '').split('#').pop(); throw error; }
    return result;
  }
  return {
    async signIn(email, password) {
      const r = await cognito('InitiateAuth', {ClientId: clientId, AuthFlow: 'USER_PASSWORD_AUTH',
        AuthParameters: {USERNAME: email, PASSWORD: password}});
      if (r.ChallengeName === 'NEW_PASSWORD_REQUIRED') {
        challenge = {session: r.Session, username: r.ChallengeParameters?.USER_ID_FOR_SRP || email,
          email, required: JSON.parse(r.ChallengeParameters?.requiredAttributes || '[]')};
        return {newPasswordRequired: true};
      }
      if (!r.AuthenticationResult) throw new Error('This account requires an authentication step not supported here. Contact the workspace owner.');
      token = r.AuthenticationResult.IdToken;
      return {signedIn: true};
    },
    async completeNewPassword(password) {
      if (!challenge) throw new Error('Please sign in again.');
      const responses = {USERNAME: challenge.username, NEW_PASSWORD: password};
      for (const name of challenge.required) {
        if (name === 'email' || name === 'userAttributes.email') responses['userAttributes.email'] = challenge.email;
        else throw new Error('Complete the required account attributes in Cognito, then sign in again.');
      }
      const r = await cognito('RespondToAuthChallenge', {ClientId: clientId,
        ChallengeName: 'NEW_PASSWORD_REQUIRED', Session: challenge.session, ChallengeResponses: responses});
      if (!r.AuthenticationResult) throw new Error('Account setup requires another authentication step.');
      token = r.AuthenticationResult.IdToken; challenge = null;
      return {signedIn: true};
    },
    // Display only: the API independently validates the JWT for authorization.
    getDisplayName() {
      if (!token) return '';
      try {
        const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
        const bytes = Uint8Array.from(atob(part), c => c.charCodeAt(0));
        const claims = JSON.parse(new TextDecoder().decode(bytes));
        return typeof claims.name === 'string' ? claims.name.trim().slice(0, 100) : '';
      } catch { return ''; }
    },
    isSignedIn() { return !!token; },
    cancelChallenge() { challenge = null; },
    async signUp(email, password, name) {
      // Only works if the owner explicitly enables self-sign-up in the SAM template.
      return cognito('SignUp', {ClientId: clientId, Username: email, Password: password,
        UserAttributes: [{Name: 'email', Value: email}, {Name: 'name', Value: name}]});
    },
    confirmSignUp(email, code) {
      return cognito('ConfirmSignUp', {ClientId: clientId, Username: email, ConfirmationCode: code});
    },
    resendSignUpCode(email) { return cognito('ResendConfirmationCode', {ClientId: clientId, Username: email}); },
    signOut() { token = null; challenge = null; },
    async ask({ question = '', document = '', mode = 'chat' }) {

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 32000);
      try {
        const authenticated = !!token;
        const headers = {'Content-Type': 'application/json'};
        if (authenticated) headers.Authorization = `Bearer ${token}`;
        const r = await fetch(apiUrl.replace(/\/$/, '') + (authenticated ? '/chat' : '/free'), {method: 'POST',
          headers,
          body: JSON.stringify({question, document, mode}), signal: controller.signal});
        const result = await r.json();
        if (!authenticated && r.status === 404) throw new Error('Free access is being enabled. The owner needs to deploy the Free backend update.');
        if (r.status === 401) { token = null; throw new Error('Your session expired. Please sign in again.'); }
        if (!r.ok) throw new Error(result.error || result.message || 'Thinking AI is unavailable.');
        return result;
      } finally { clearTimeout(timeout); }
    }
  };
}
