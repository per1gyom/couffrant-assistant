import 'package:dio/dio.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';
import 'package:cookie_jar/cookie_jar.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:path_provider/path_provider.dart';
import '../config/api_config.dart';

/// Client HTTP singleton avec gestion des cookies de session.
/// Le backend Raya utilise des cookies de session (pas JWT).
/// Sur mobile : PersistCookieJar sur disque (survit aux redémarrages).
/// Sur web : CookieJar en mémoire (le navigateur gère les cookies).
class ApiService {
  static ApiService? _instance;
  late final Dio dio;
  CookieJar? cookieJar;
  bool _initialized = false;

  ApiService._();

  static ApiService get instance {
    _instance ??= ApiService._();
    return _instance!;
  }

  Future<void> init() async {
    if (_initialized) return;

    dio = Dio(BaseOptions(
      baseUrl: ApiConfig.baseUrl,
      connectTimeout: Duration(seconds: ApiConfig.connectTimeout),
      receiveTimeout: Duration(seconds: ApiConfig.receiveTimeout),
      sendTimeout: Duration(seconds: ApiConfig.sendTimeout),
      followRedirects: false,
      // On garde permissif (< 500) pour que login puisse lire un 401 comme
      // "identifiant incorrect" au lieu de throw. Un intercepteur dedie
      // pourra etre ajoute plus tard pour gerer 401/403 sur les routes
      // authentifiees (redirection login auto).
      validateStatus: (status) => status != null && status < 500,
      headers: {
        'Accept': 'application/json',
      },
    ));

    // Sur mobile : cookie jar PERSISTANT sur disque (survit aux redemarrages)
    // Sur web : le navigateur gere les cookies automatiquement
    if (!kIsWeb) {
      try {
        final dir = await getApplicationDocumentsDirectory();
        final cookiePath = '${dir.path}/.raya_cookies/';
        cookieJar = PersistCookieJar(
          storage: FileStorage(cookiePath),
          ignoreExpires: false,
        );
      } catch (_) {
        // Fallback si le file system echoue (tests, etc.) : memory jar
        cookieJar = CookieJar();
      }
      dio.interceptors.add(CookieManager(cookieJar!));
    } else {
      // Sur web, activer withCredentials pour envoyer les cookies
      dio.options.extra['withCredentials'] = true;
    }

    _initialized = true;
  }

  /// Efface tous les cookies (déconnexion)
  Future<void> clearCookies() async {
    if (cookieJar != null) {
      await cookieJar!.deleteAll();
    }
  }

  /// POST form-encoded (pour le login)
  Future<Response> postForm(String path, Map<String, dynamic> data) async {
    return dio.post(
      path,
      data: FormData.fromMap(data),
      options: Options(
        contentType: 'application/x-www-form-urlencoded',
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
