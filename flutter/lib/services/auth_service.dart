import '../config/api_config.dart';
import 'api_service.dart';

class AuthResult {
  final bool success;
  final String? error;
  AuthResult({required this.success, this.error});
}

class AuthService {
  final ApiService _api = ApiService.instance;
  static String? _cachedUsername;
  static bool _isLoggedIn = false;

  Future<AuthResult> login(String username, String password) async {
    try {
      final response = await _api.postForm(
        ApiConfig.loginEndpoint,
        {'username': username, 'password': password},
      );

      // Cas 1 : redirect 302/303 vers /chat (natif iOS)
      if (response.statusCode == 303 || response.statusCode == 302) {
        final location = response.headers['location']?.first ?? '';
        if (location.contains('/chat') || location.contains('/forced-reset')) {
          _cachedUsername = username;
          _isLoggedIn = true;
          return AuthResult(success: true);
        }
      }

      // Cas 2 : 200 = le navigateur a suivi la redirection (web Chrome)
      // Le backend renvoie le HTML de /chat si login OK
      // ou le HTML de /login-app si login KO (avec status 200 parfois)
      if (response.statusCode == 200) {
        // Verifier si la session est active en appelant /health
        try {
          final healthCheck = await _api.get(ApiConfig.healthEndpoint);
          if (healthCheck.statusCode == 200) {
            _cachedUsername = username;
            _isLoggedIn = true;
            return AuthResult(success: true);
          }
        } catch (_) {}

        // Si health check echoue, le login a probablement echoue aussi
        // Verifier si la reponse contient "error" (page login avec erreur)
        final body = response.data?.toString() ?? '';
        if (body.contains('error') || body.contains('incorrect')) {
          return AuthResult(
            success: false,
            error: 'Identifiant ou mot de passe incorrect.',
          );
        }

        // Sinon on considere que c'est OK (redirect suivie)
        _cachedUsername = username;
        _isLoggedIn = true;
        return AuthResult(success: true);
      }

      // Cas 3 : 401 explicite
      if (response.statusCode == 401) {
        return AuthResult(
          success: false,
          error: 'Identifiant ou mot de passe incorrect.',
        );
      }

      return AuthResult(
        success: false,
        error: 'Erreur de connexion (${response.statusCode}).',
      );
    } catch (e) {
      return AuthResult(
        success: false,
        error: 'Impossible de joindre Raya.',
      );
    }
  }

  Future<void> logout() async {
    try { await _api.get(ApiConfig.logoutEndpoint); } catch (_) {}
    await _api.clearCookies();
    _cachedUsername = null;
    _isLoggedIn = false;
  }

  Future<bool> isLoggedIn() async {
    if (!_isLoggedIn) return false;
    try {
      final r = await _api.get(ApiConfig.healthEndpoint);
      return r.statusCode == 200;
    } catch (_) { return false; }
  }

  String? getUsername() => _cachedUsername;
}
