import 'package:dio/dio.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';
import 'package:cookie_jar/cookie_jar.dart';
import 'package:path_provider/path_provider.dart';
import '../config/api_config.dart';

/// Client HTTP singleton avec gestion des cookies de session.
/// Le backend Raya utilise des cookies de session (pas JWT).
/// On reproduit le comportement du navigateur web.
class ApiService {
  static ApiService? _instance;
  late final Dio dio;
  late final PersistCookieJar cookieJar;
  bool _initialized = false;

  ApiService._();

  static ApiService get instance {
    _instance ??= ApiService._();
    return _instance!;
  }

  Future<void> init() async {
    if (_initialized) return;

    // Cookie jar persistant (survit aux redémarrages de l'app)
    final dir = await getApplicationDocumentsDirectory();
    cookieJar = PersistCookieJar(
      storage: FileStorage('${dir.path}/.cookies/'),
    );

    dio = Dio(BaseOptions(
      baseUrl: ApiConfig.baseUrl,
      connectTimeout: Duration(seconds: ApiConfig.connectTimeout),
      receiveTimeout: Duration(seconds: ApiConfig.receiveTimeout),
      // Important : suivre les redirections mais ne pas les exécuter
      // automatiquement (pour gérer le login qui redirige)
      followRedirects: false,
      validateStatus: (status) => status != null && status < 500,
      headers: {
        'Accept': 'application/json',
      },
    ));

    // Intercepteur cookies — gère automatiquement les cookies de session
    dio.interceptors.add(CookieManager(cookieJar));

    _initialized = true;
  }

  /// Vérifie si une session active existe (cookie valide)
  Future<bool> hasActiveSession() async {
    try {
      final uri = Uri.parse(ApiConfig.baseUrl);
      final cookies = await cookieJar.loadForRequest(uri);
      return cookies.any((c) => c.name == 'session');
    } catch (_) {
      return false;
    }
  }

  /// Efface tous les cookies (déconnexion)
  Future<void> clearCookies() async {
    await cookieJar.deleteAll();
  }

  /// POST form-encoded (pour le login)
  Future<Response> postForm(String path, Map<String, dynamic> data) async {
    return dio.post(
      path,
      data: FormData.fromMap(data),
      options: Options(
        contentType: 'application/x-www-form-urlencoded',
        // Le login redirige vers /chat en cas de succès (302/303)
        followRedirects: false,
        validateStatus: (status) => status != null && status < 500,
      ),
    );
  }

  /// POST JSON (pour /raya, /speak, /feedback, etc.)
  Future<Response> postJson(String path, Map<String, dynamic> data) async {
    return dio.post(
      path,
      data: data,
      options: Options(contentType: 'application/json'),
    );
  }

  /// GET (pour /health, /chat/history, etc.)
  Future<Response> get(String path, {Map<String, dynamic>? params}) async {
    return dio.get(path, queryParameters: params);
  }
}
