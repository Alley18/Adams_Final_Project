import 'dart:async';
import 'dart:math' as math;
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import 'package:firebase_database/firebase_database.dart';

import '../widgets/screen_frame.dart';

// ── Route option model ─────────────────────────────────────────────────────

class RouteOption {
  const RouteOption({
    required this.icon,
    required this.label,
    required this.time,
    required this.description,
    required this.color,
    required this.emotion,
  });

  final IconData icon;
  final String label;
  final String time;
  final String description;
  final Color color;
  final String emotion;
}

const _routeOptions = [
  RouteOption(
    icon: Icons.self_improvement,
    label: 'Relaxed',
    time: '...',
    description: 'Parks, cafes, scenic detour',
    color: Color(0xFFFF9F1C),
    emotion: 'relaxed',
  ),
  RouteOption(
    icon: Icons.sentiment_very_satisfied,
    label: 'Happy',
    time: '...',
    description: 'Lively streets, points of interest',
    color: Color(0xFFF4C430),
    emotion: 'happy',
  ),
  RouteOption(
    icon: Icons.flash_on,
    label: 'Stressed',
    time: '...',
    description: 'Fastest, fewest traffic lights',
    color: Color(0xFFE6B325),
    emotion: 'stressed',
  ),
  RouteOption(
    icon: Icons.bedtime,
    label: 'Tired',
    time: '...',
    description: 'Safe main roads, no sharp turns',
    color: Color(0xFF8B9FD4),
    emotion: 'tired',
  ),
  RouteOption(
    icon: Icons.center_focus_strong,
    label: 'Focused',
    time: '...',
    description: 'Efficient, low distraction',
    color: Color(0xFFFFC857),
    emotion: 'focused',
  ),
  RouteOption(
    icon: Icons.remove_circle_outline,
    label: 'Neutral',
    time: '...',
    description: 'Balanced route',
    color: Color(0xFF888888),
    emotion: 'neutral',
  ),
];

const Duration _rerouteCooldown = Duration(minutes: 10);

// ── Screen ─────────────────────────────────────────────────────────────────

class MoodRouteScreen extends StatefulWidget {
  const MoodRouteScreen({super.key});

  @override
  State<MoodRouteScreen> createState() => _MoodRouteScreenState();
}

class _MoodRouteScreenState extends State<MoodRouteScreen>
    with TickerProviderStateMixin {
  final MapController _mapController = MapController();
  final TextEditingController _searchController = TextEditingController();
  final Dio _dio = Dio();

  // ⚠️  On a physical Android device 127.0.0.1 = the phone itself, NOT your PC.
  //     Run `ipconfig` on Windows, find your PC's IPv4 (e.g. 192.168.0.x) and
  //     put it here. Keep port 5000.
  final String _backendUrl = 'http://172.19.2.209:5000'; // Pi route server

  late final DatabaseReference _firebaseRef;
  StreamSubscription<DatabaseEvent>? _firebaseSub;

  LatLng? _currentLocation;
  LatLng? _destination;
  String _destinationName = '';

  int _selectedIndex = 0;
  int? _autoSelectedIndex;

  final Map<String, List<LatLng>> _routePoints    = {};
  final Map<String, String>       _routeDurations = {};

  bool _loadingLocation = true;
  bool _loadingRoute    = false;
  bool _showSearch      = false;

  List<Map<String, dynamic>> _searchResults = [];
  bool _searchingPlace = false;

  String _currentDominantEmotion = 'neutral';
  DateTime? _lastRerouteTime;
  bool _tripInProgress = false;

  String? _rerouteBannerMessage;
  Timer? _bannerTimer;

  // ── Direction pulse animation ──────────────────────────────────────────
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;
  int _navSegmentIndex = 0;
  Timer? _navTimer;

  @override
  void initState() {
    super.initState();
    _initLocation();
    _subscribeToFirebase();

    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat(reverse: true);
    _pulseAnimation = Tween<double>(begin: 1.0, end: 1.6).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _searchController.dispose();
    _firebaseSub?.cancel();
    _bannerTimer?.cancel();
    _navTimer?.cancel();
    _pulseController.dispose();
    _dio.close();
    super.dispose();
  }

  // ── Firebase ───────────────────────────────────────────────────────────

  void _subscribeToFirebase() {
    _firebaseRef = FirebaseDatabase.instance.ref('driver_status');
    _firebaseSub = _firebaseRef.onValue.listen((event) {
      final data = event.snapshot.value as Map<dynamic, dynamic>?;
      if (data == null) return;
      final newDominant =
          (data['dominant_emotion'] as String? ?? 'neutral').toLowerCase();
      if (newDominant != _currentDominantEmotion) {
        _currentDominantEmotion = newDominant;
        _onDominantEmotionChanged(newDominant);
      }
    });
  }

  void _onDominantEmotionChanged(String newEmotion) {
    if (!_tripInProgress || _destination == null) return;
    final now = DateTime.now();
    if (_lastRerouteTime != null &&
        now.difference(_lastRerouteTime!) < _rerouteCooldown) {
      return;
    }

    final newIndex = _routeOptions.indexWhere((r) => r.emotion == newEmotion);
    if (newIndex == -1 || newIndex == _selectedIndex) return;

    _lastRerouteTime   = now;
    _autoSelectedIndex = newIndex;
    setState(() => _selectedIndex = newIndex);
    _fitMapToRoute();
    _showRerouteBanner(newEmotion);
    _resetNavProgress();
  }

  void _showRerouteBanner(String emotion) {
    _bannerTimer?.cancel();
    setState(() => _rerouteBannerMessage =
        'Route updated for your mood: ${emotion.toUpperCase()}');
    _bannerTimer = Timer(const Duration(seconds: 4), () {
      if (mounted) setState(() => _rerouteBannerMessage = null);
    });
  }

  // ── Location ───────────────────────────────────────────────────────────

  Future<void> _initLocation() async {
    try {
      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.deniedForever ||
          permission == LocationPermission.denied) {
        setState(() => _loadingLocation = false);
        return;
      }
      final pos = await Geolocator.getCurrentPosition(
        locationSettings:
            const LocationSettings(accuracy: LocationAccuracy.high),
      );
      setState(() {
        _currentLocation = LatLng(pos.latitude, pos.longitude);
        _loadingLocation = false;
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_currentLocation != null) {
          _mapController.move(_currentLocation!, 14);
        }
      });
    } catch (e) {
      setState(() => _loadingLocation = false);
    }
  }

  // ── Place search (Nominatim) ───────────────────────────────────────────

  Future<void> _searchPlaces(String query) async {
    if (query.trim().isEmpty) {
      setState(() => _searchResults = []);
      return;
    }
    setState(() => _searchingPlace = true);
    try {
      final response = await _dio.get(
        'https://nominatim.openstreetmap.org/search',
        queryParameters: {
          'q': query,
          'format': 'json',
          'limit': '5',
          'addressdetails': '1',
        },
        options: Options(headers: {'User-Agent': 'ADAMS-Mobile-App/1.0'}),
      );
      final results = (response.data as List).map((item) {
        return {
          'name': item['display_name'] as String,
          'lat':  double.parse(item['lat'] as String),
          'lon':  double.parse(item['lon'] as String),
        };
      }).toList();
      setState(() {
        _searchResults  = results;
        _searchingPlace = false;
      });
    } catch (e) {
      setState(() => _searchingPlace = false);
    }
  }

  // ── Route fetch ────────────────────────────────────────────────────────

  Future<void> _fetchAllRoutes() async {
    if (_currentLocation == null || _destination == null) return;
    setState(() {
      _loadingRoute = true;
      _routePoints.clear();
      _routeDurations.clear();
    });
    for (final option in _routeOptions) {
      await _fetchRouteFromBackend(option.emotion);
    }
    setState(() => _loadingRoute = false);
    // Always fit + start nav — fallback routes also populate _routePoints
    _fitMapToRoute();
    _startNavProgress();
  }

  Future<void> _fetchRouteFromBackend(String emotion) async {
    try {
      final origin = '${_currentLocation!.longitude},${_currentLocation!.latitude}';
      final dest   = '${_destination!.longitude},${_destination!.latitude}';

      final response = await _dio.post(
        '$_backendUrl/route',
        data: {
          'origin':      origin,
          'destination': dest,
          'emotion':     emotion,
        },
        options: Options(
          sendTimeout:    const Duration(seconds: 8),
          receiveTimeout: const Duration(seconds: 8),
        ),
      );

      final data = response.data as Map<String, dynamic>;

      if (data['status'] == 'mock') {
        final coords = (data['coordinates'] as List).map((c) {
          return LatLng(c[0] as double, c[1] as double);
        }).toList();
        setState(() {
          _routePoints[emotion]    = coords;
          _routeDurations[emotion] = data['duration'] ?? '-- min';
        });
      } else if (data['routes'] != null) {
        final route = data['routes'][0];
        final List<LatLng> coords = [];
        for (var section in route['sections']) {
          for (var road in section['roads']) {
            for (var i = 0; i < (road['vertexes'] as List).length; i += 2) {
              coords.add(LatLng(
                road['vertexes'][i + 1] as double,
                road['vertexes'][i]     as double,
              ));
            }
          }
        }
        final durationSec = route['summary']['duration'] as int;
        final minutes     = (durationSec / 60).round();
        setState(() {
          _routePoints[emotion]    = coords;
          _routeDurations[emotion] = '$minutes min';
        });
      }
    } catch (e) {
      // Backend unreachable (e.g. 127.0.0.1 from a physical device).
      // Fallback: draw a visible arc so route lines always appear.
      debugPrint('Route backend error ($emotion): $e — using fallback');
      _useFallbackRoute(emotion);
    }
  }

  /// Straight-line arc fallback with per-emotion lateral offsets.
  void _useFallbackRoute(String emotion) {
    if (_currentLocation == null || _destination == null) return;
    final src = _currentLocation!;
    final dst = _destination!;

    const offsets = {
      'relaxed':  0.0008,
      'happy':    0.0004,
      'stressed': 0.0,
      'tired':   -0.0004,
      'focused': -0.0008,
      'neutral':  0.0012,
    };
    final offset = offsets[emotion] ?? 0.0;

    const steps = 20;
    final coords = <LatLng>[];
    for (var i = 0; i <= steps; i++) {
      final t   = i / steps;
      final lat = src.latitude  + (dst.latitude  - src.latitude)  * t;
      final lon = src.longitude + (dst.longitude - src.longitude) * t
                  + offset * math.sin(t * math.pi);
      coords.add(LatLng(lat, lon));
    }

    const earthR = 6371.0;
    final dLat = (dst.latitude  - src.latitude)  * math.pi / 180;
    final dLon = (dst.longitude - src.longitude) * math.pi / 180;
    final a = math.sin(dLat/2)*math.sin(dLat/2) +
              math.cos(src.latitude*math.pi/180) *
              math.cos(dst.latitude*math.pi/180) *
              math.sin(dLon/2)*math.sin(dLon/2);
    final distKm = earthR * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a));
    final minutes = (distKm / 30 * 60).round().clamp(1, 999);

    setState(() {
      _routePoints[emotion]    = coords;
      _routeDurations[emotion] = '~$minutes min';
    });
  }

  void _fitMapToRoute() {
    final points = _routePoints[_routeOptions[_selectedIndex].emotion] ?? [];
    if (points.isEmpty) return;

    double minLat = points.first.latitude,  maxLat = points.first.latitude;
    double minLon = points.first.longitude, maxLon = points.first.longitude;
    for (final p in points) {
      if (p.latitude  < minLat) minLat = p.latitude;
      if (p.latitude  > maxLat) maxLat = p.latitude;
      if (p.longitude < minLon) minLon = p.longitude;
      if (p.longitude > maxLon) maxLon = p.longitude;
    }
    _mapController.fitCamera(
      CameraFit.bounds(
        bounds: LatLngBounds(
            LatLng(minLat, minLon), LatLng(maxLat, maxLon)),
        padding: const EdgeInsets.all(60),
      ),
    );
  }

  void _selectDestination(Map<String, dynamic> result) {
    setState(() {
      _destination     = LatLng(result['lat'] as double, result['lon'] as double);
      _destinationName = result['name'] as String;
      _searchResults   = [];
      _showSearch      = false;
      _searchController.text = _destinationName;
      _tripInProgress  = true;
      _lastRerouteTime = null;
    });
    _fetchAllRoutes();
  }

  // ── Nav progress simulator ─────────────────────────────────────────────
  // Simulates a moving dot along the selected route to give direction sense.

  void _startNavProgress() {
    _navTimer?.cancel();
    _navSegmentIndex = 0;
    _navTimer = Timer.periodic(const Duration(milliseconds: 400), (_) {
      final points =
          _routePoints[_routeOptions[_selectedIndex].emotion] ?? [];
      if (points.isEmpty || !mounted) return;
      setState(() {
        _navSegmentIndex = (_navSegmentIndex + 1) % points.length;
      });
    });
  }

  void _resetNavProgress() {
    setState(() => _navSegmentIndex = 0);
  }

  // ── Computed route segments ────────────────────────────────────────────

  List<LatLng> get _travelledPoints {
    final points = _routePoints[_routeOptions[_selectedIndex].emotion] ?? [];
    if (points.isEmpty || _navSegmentIndex >= points.length) return [];
    return points.sublist(0, _navSegmentIndex + 1);
  }

  List<LatLng> get _remainingPoints {
    final points = _routePoints[_routeOptions[_selectedIndex].emotion] ?? [];
    if (points.isEmpty) return [];
    if (_navSegmentIndex >= points.length) return points;
    return points.sublist(_navSegmentIndex);
  }

  LatLng? get _navPosition {
    final points = _routePoints[_routeOptions[_selectedIndex].emotion] ?? [];
    if (points.isEmpty) return null;
    final idx = _navSegmentIndex.clamp(0, points.length - 1);
    return points[idx];
  }

  // ── Bearing helper ─────────────────────────────────────────────────────

  /// Returns bearing in radians from [p1] to [p2].
  double _bearing(LatLng p1, LatLng p2) {
    final dLon = p2.longitude - p1.longitude;
    final dLat = p2.latitude  - p1.latitude;
    return math.atan2(dLon, dLat); // radians, clockwise from north
  }

  // ── Build ──────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return ScreenFrame(
      title:    'Mood Route',
      subtitle: 'Maps',
      child: Column(
        children: [
          _buildSearchBar(),
          const SizedBox(height: 8),
          if (_rerouteBannerMessage != null) _buildRerouteBanner(),
          // Map uses flex: 5 so it stays dominant regardless of panel below
          Expanded(
            flex: 5,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Stack(
                children: [
                  _buildMap(),
                  if (_loadingLocation)
                    const Center(child: CircularProgressIndicator()),
                  if (_loadingRoute) _buildLoadingOverlay(),
                  _buildMoodChip(),
                  _buildLocateButton(),
                ],
              ),
            ),
          ),
          const SizedBox(height: 10),
          if (_showSearch && _searchResults.isNotEmpty) _buildSearchResults(),
          if (_destination != null) _buildRoutePanel(),
        ],
      ),
    );
  }

  // ── Sub-widgets ────────────────────────────────────────────────────────

  Widget _buildRerouteBanner() {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      margin:  const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color:        const Color(0xFFFF9F1C).withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border:       Border.all(color: const Color(0xFFFF9F1C), width: 1),
      ),
      child: Row(
        children: [
          const Icon(Icons.route, color: Color(0xFFFF9F1C), size: 16),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              _rerouteBannerMessage!,
              style: const TextStyle(color: Color(0xFFFF9F1C), fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingOverlay() {
    return Positioned(
      top: 12, right: 12,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.black87,
          borderRadius: BorderRadius.circular(20),
        ),
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 12, height: 12,
              child: CircularProgressIndicator(
                  strokeWidth: 2, color: Colors.white),
            ),
            SizedBox(width: 8),
            Text('Fetching routes…',
                style: TextStyle(fontSize: 11, color: Colors.white)),
          ],
        ),
      ),
    );
  }

  Widget _buildMoodChip() {
    return Positioned(
      top: 12, left: 12,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: Colors.black87,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(
          'Mood: ${_currentDominantEmotion.toUpperCase()}',
          style: const TextStyle(color: Colors.white70, fontSize: 11),
        ),
      ),
    );
  }

  Widget _buildLocateButton() {
    return Positioned(
      bottom: 12, right: 12,
      child: FloatingActionButton.small(
        onPressed: () {
          if (_currentLocation != null) {
            _mapController.move(_currentLocation!, 15);
          }
        },
        backgroundColor: const Color(0xFF1C232B),
        child: const Icon(Icons.my_location, size: 20),
      ),
    );
  }

  Widget _buildSearchBar() {
    return TextField(
      controller: _searchController,
      style: const TextStyle(color: Colors.white, fontSize: 14),
      decoration: InputDecoration(
        hintText:   'Where do you want to go?',
        hintStyle:  const TextStyle(color: Colors.white38, fontSize: 14),
        prefixIcon: const Icon(Icons.search, color: Colors.white54, size: 20),
        suffixIcon: _searchController.text.isNotEmpty
            ? IconButton(
                icon: const Icon(Icons.clear,
                    color: Colors.white38, size: 18),
                onPressed: () {
                  _searchController.clear();
                  _navTimer?.cancel();
                  setState(() {
                    _searchResults   = [];
                    _showSearch      = false;
                    _destination     = null;
                    _destinationName = '';
                    _routePoints.clear();
                    _routeDurations.clear();
                    _tripInProgress  = false;
                    _navSegmentIndex = 0;
                  });
                },
              )
            : null,
        filled:    true,
        fillColor: const Color(0xFF1C232B),
        border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8),
            borderSide:   BorderSide.none),
        focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8),
            borderSide:
                const BorderSide(color: Color(0xFFFF9F1C), width: 1.5)),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      ),
      onTap:     () => setState(() => _showSearch = true),
      onChanged: _searchPlaces,
    );
  }

  Widget _buildSearchResults() {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color:        const Color(0xFF1C232B),
        borderRadius: BorderRadius.circular(8),
      ),
      child: _searchingPlace
          ? const Padding(
              padding: EdgeInsets.all(16),
              child:   Center(
                  child: CircularProgressIndicator(strokeWidth: 2)),
            )
          : ListView.separated(
              shrinkWrap: true,
              physics:    const NeverScrollableScrollPhysics(),
              itemCount:  _searchResults.length,
              separatorBuilder: (_, __) =>
                  const Divider(height: 1, color: Colors.white12),
              itemBuilder: (context, i) {
                final r = _searchResults[i];
                return ListTile(
                  dense:   true,
                  leading: const Icon(Icons.location_on,
                      color: Color(0xFFFF9F1C), size: 18),
                  title: Text(
                    r['name'] as String,
                    style: const TextStyle(
                        color: Colors.white, fontSize: 12),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  onTap: () => _selectDestination(r),
                );
              },
            ),
    );
  }

  // ── Map ────────────────────────────────────────────────────────────────

  Widget _buildMap() {
    final selectedEmotion = _routeOptions[_selectedIndex].emotion;
    final selectedColor   = _routeOptions[_selectedIndex].color;
    final navPos          = _navPosition;
    final travelled       = _travelledPoints;
    final remaining       = _remainingPoints;
    final isNavigating    = _tripInProgress && navPos != null;

    return FlutterMap(
      mapController: _mapController,
      options: MapOptions(
        initialCenter: _currentLocation ?? const LatLng(37.5665, 126.9780),
        initialZoom:   13,
        onTap: (_, __) => setState(() {
          _showSearch    = false;
          _searchResults = [];
        }),
      ),
      children: [
        TileLayer(
          urlTemplate:          'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'com.example.adams_mobile',
        ),

        // ── Ghost routes (non-selected) ──────────────────────────────
        for (var i = 0; i < _routeOptions.length; i++)
          if (i != _selectedIndex &&
              _routePoints[_routeOptions[i].emotion] != null)
            PolylineLayer(
              polylines: [
                Polyline(
                  points:      _routePoints[_routeOptions[i].emotion]!,
                  strokeWidth: 2.5,
                  color: _routeOptions[i].color.withValues(alpha: 0.13),
                ),
              ],
            ),

        // ── Selected route: full line (pre-nav, or fallback) ─────────
        if (!isNavigating && _routePoints[selectedEmotion] != null)
          PolylineLayer(
            polylines: [
              Polyline(
                points:      _routePoints[selectedEmotion]!,
                strokeWidth: 5,
                color:       selectedColor,
              ),
            ],
          ),

        // ── Travelled portion: bright solid line ─────────────────────
        if (isNavigating && travelled.length > 1)
          PolylineLayer(
            polylines: [
              Polyline(
                points:      travelled,
                strokeWidth: 6,
                color:       selectedColor,
              ),
            ],
          ),

        // ── Remaining portion: dashed + dimmed ───────────────────────
        if (isNavigating && remaining.length > 1)
          PolylineLayer(
            polylines: [
              Polyline(
                points:      remaining,
                strokeWidth: 4,
                color:       selectedColor.withValues(alpha: 0.38),
                pattern:
                    StrokePattern.dashed(segments: [14, 7]),
              ),
            ],
          ),

        // ── Direction arrow markers along remaining path ──────────────
        if (isNavigating && remaining.length > 4)
          MarkerLayer(
            markers: _buildDirectionArrows(remaining, selectedColor),
          ),

        // ── Markers ──────────────────────────────────────────────────
        MarkerLayer(
          markers: [
            // Origin dot
            if (_currentLocation != null)
              Marker(
                point:  _currentLocation!,
                width:  44,
                height: 44,
                child:  _buildOriginMarker(),
              ),

            // Animated nav dot (moving "car")
            if (isNavigating)
              Marker(
                point:  navPos,
                width:  36,
                height: 36,
                child: AnimatedBuilder(
                  animation: _pulseAnimation,
                  builder: (context, _) => Transform.scale(
                    scale: _pulseAnimation.value,
                    child: Container(
                      decoration: BoxDecoration(
                        color:  selectedColor,
                        shape:  BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 2.5),
                        boxShadow: [
                          BoxShadow(
                            color:       selectedColor.withValues(alpha: 0.6),
                            blurRadius:  14,
                            spreadRadius: 2,
                          ),
                        ],
                      ),
                      child: const Icon(
                          Icons.navigation, size: 16, color: Colors.white),
                    ),
                  ),
                ),
              ),

            // Destination flag
            if (_destination != null)
              Marker(
                point:  _destination!,
                width:  44,
                height: 54,
                child:  _buildDestinationMarker(selectedColor),
              ),
          ],
        ),
      ],
    );
  }

  Widget _buildOriginMarker() {
    return Container(
      decoration: BoxDecoration(
        color:  const Color(0xFFFF9F1C),
        shape:  BoxShape.circle,
        border: Border.all(color: Colors.white, width: 3),
        boxShadow: [
          BoxShadow(
            color:      const Color(0xFFFF9F1C).withValues(alpha: 0.5),
            blurRadius: 8,
          ),
        ],
      ),
      child: const Icon(Icons.my_location, size: 18, color: Colors.white),
    );
  }

  Widget _buildDestinationMarker(Color color) {
    return Column(
      children: [
        Container(
          width:  34,
          height: 34,
          decoration: BoxDecoration(
            color:  color,
            shape:  BoxShape.circle,
            border: Border.all(color: Colors.white, width: 2.5),
            boxShadow: [
              BoxShadow(color: color.withValues(alpha: 0.5), blurRadius: 8),
            ],
          ),
          child: const Icon(Icons.flag, size: 17, color: Colors.white),
        ),
        Container(width: 2, height: 14, color: color),
      ],
    );
  }

  /// Builds directional arrow markers spaced evenly along [points].
  List<Marker> _buildDirectionArrows(List<LatLng> points, Color color) {
    if (points.length < 5) return [];
    final markers = <Marker>[];
    // Place ~4 arrows evenly along the remaining path
    final step = (points.length / 4).round().clamp(1, points.length);
    for (var i = step; i < points.length - 1; i += step) {
      final angle = _bearing(points[i - 1], points[i]);
      markers.add(Marker(
        point:  points[i],
        width:  20,
        height: 20,
        child: Transform.rotate(
          angle: angle,
          child: Icon(
            Icons.navigation,
            size:  14,
            color: color.withValues(alpha: 0.75),
          ),
        ),
      ));
    }
    return markers;
  }

  // ── Route panel — horizontal chips + detail card ───────────────────────
  // Fixed height regardless of how many options exist → map never shrinks.

  Widget _buildRoutePanel() {
    final selected = _routeOptions[_selectedIndex];
    final duration = _routeDurations[selected.emotion] ?? '...';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Horizontal scrollable mood chips (46 px fixed height)
        SizedBox(
          height: 46,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding:         const EdgeInsets.symmetric(horizontal: 2),
            itemCount:       _routeOptions.length,
            separatorBuilder: (_, __) => const SizedBox(width: 8),
            itemBuilder: (context, i) {
              final opt   = _routeOptions[i];
              final isSel = i == _selectedIndex;
              final isAuto = i == _autoSelectedIndex;
              return GestureDetector(
                onTap: () {
                  setState(() {
                    _selectedIndex     = i;
                    _autoSelectedIndex = null;
                  });
                  _fitMapToRoute();
                  _resetNavProgress();
                },
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  padding: const EdgeInsets.symmetric(horizontal: 14),
                  decoration: BoxDecoration(
                    color: isSel
                        ? opt.color.withValues(alpha: 0.20)
                        : const Color(0xFF1C232B),
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(
                      color: isSel ? opt.color : Colors.white12,
                      width: isSel ? 1.5 : 1,
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(opt.icon,
                          size:  15,
                          color: isSel ? opt.color : Colors.white38),
                      const SizedBox(width: 6),
                      Text(
                        opt.label,
                        style: TextStyle(
                          fontSize:   13,
                          fontWeight: isSel
                              ? FontWeight.w700
                              : FontWeight.w400,
                          color: isSel ? opt.color : Colors.white54,
                        ),
                      ),
                      if (isAuto) ...[
                        const SizedBox(width: 4),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 4, vertical: 1),
                          decoration: BoxDecoration(
                            color:        opt.color.withValues(alpha: 0.25),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            'AUTO',
                            style: TextStyle(
                              fontSize:   7,
                              color:      opt.color,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              );
            },
          ),
        ),
        const SizedBox(height: 10),

        // Selected route detail card (fixed height ~72 px)
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: selected.color.withValues(alpha: 0.11),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
                color: selected.color.withValues(alpha: 0.4), width: 1),
          ),
          child: Row(
            children: [
              Container(
                width:  44,
                height: 44,
                decoration: BoxDecoration(
                  color:  selected.color.withValues(alpha: 0.18),
                  shape:  BoxShape.circle,
                ),
                child: Icon(selected.icon,
                    color: selected.color, size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${selected.label} Route',
                      style: TextStyle(
                        color:      selected.color,
                        fontWeight: FontWeight.w700,
                        fontSize:   14,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      selected.description,
                      style: const TextStyle(
                          color: Colors.white54, fontSize: 12),
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    duration,
                    style: TextStyle(
                      color:      selected.color,
                      fontWeight: FontWeight.w800,
                      fontSize:   18,
                    ),
                  ),
                  const Text(
                    'est. time',
                    style:
                        TextStyle(color: Colors.white38, fontSize: 10),
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }
}
