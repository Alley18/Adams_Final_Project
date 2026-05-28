import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import '../widgets/screen_frame.dart';

// ── Route option model ────────────────────────────────────────────────────────

class RouteOption {
  const RouteOption({
    required this.icon,
    required this.label,
    required this.time,
    required this.description,
    required this.color,
    required this.emotion, // Maps to backend emotion logic
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
    icon: Icons.sentiment_satisfied,
    label: 'Calm',
    time: '...',
    description: 'Scenic & balanced route',
    color: Color(0xFF00A896),
    emotion: 'calm',
  ),
  RouteOption(
    icon: Icons.flash_on,
    label: 'Stressed',
    time: '...',
    description: 'Fastest route to destination',
    color: Color(0xFFE6B325),
    emotion: 'stressed',
  ),
  RouteOption(
    icon: Icons.bedtime,
    label: 'Sleepy',
    time: '...',
    description: 'Safe & simple main roads',
    color: Color(0xFF8B9FD4),
    emotion: 'sleepy',
  ),
];

// ── Screen ────────────────────────────────────────────────────────────────────

class MoodRouteScreen extends StatefulWidget {
  const MoodRouteScreen({super.key});

  @override
  State<MoodRouteScreen> createState() => _MoodRouteScreenState();
}

class _MoodRouteScreenState extends State<MoodRouteScreen> {
  final MapController _mapController = MapController();
  final TextEditingController _searchController = TextEditingController();
  final Dio _dio = Dio();

  // Replace with your actual backend URL
  final String _backendUrl = 'http://127.0.0.1:5000';

  LatLng? _currentLocation;
  LatLng? _destination;
  String _destinationName = '';

  int _selectedIndex = 0;

  // Route polylines per emotion
  final Map<String, List<LatLng>> _routePoints = {};
  final Map<String, String> _routeDurations = {};

  bool _loadingLocation = true;
  bool _loadingRoute = false;
  bool _showSearch = false;

  List<Map<String, dynamic>> _searchResults = [];
  bool _searchingPlace = false;

  @override
  void initState() {
    super.initState();
    _initLocation();
  }

  @override
  void dispose() {
    _searchController.dispose();
    _dio.close();
    super.dispose();
  }

  // ── Location ───────────────────────────────────────────────────────────────

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
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      );

      setState(() {
        _currentLocation = LatLng(pos.latitude, pos.longitude);
        _loadingLocation = false;
      });

      // Move map to current location
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_currentLocation != null) {
          _mapController.move(_currentLocation!, 14);
        }
      });
    } catch (e) {
      setState(() => _loadingLocation = false);
    }
  }

  // ── Place search (Nominatim) ───────────────────────────────────────────────

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
        options: Options(
          headers: {'User-Agent': 'ADAMS-Mobile-App/1.0'},
        ),
      );

      final results = (response.data as List).map((item) {
        return {
          'name': item['display_name'] as String,
          'lat': double.parse(item['lat'] as String),
          'lon': double.parse(item['lon'] as String),
        };
      }).toList();

      setState(() {
        _searchResults = results;
        _searchingPlace = false;
      });
    } catch (e) {
      setState(() => _searchingPlace = false);
    }
  }

  // ── Route fetch (ADAMS Backend with KakaoMap) ──────────────────────────────

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

    if (_routePoints[_routeOptions[_selectedIndex].emotion]?.isNotEmpty == true) {
      _fitMapToRoute();
    }
  }

  Future<void> _fetchRouteFromBackend(String emotion) async {
    try {
      final origin = '${_currentLocation!.longitude},${_currentLocation!.latitude}';
      final dest = '${_destination!.longitude},${_destination!.latitude}';

      final response = await _dio.post(
        '$_backendUrl/route',
        data: {
          'origin': origin,
          'destination': dest,
          'emotion': emotion,
        },
      );

      final data = response.data;

      // Handle both Mock and Real Kakao Data
      if (data['status'] == 'mock') {
        final coords = (data['coordinates'] as List).map((c) {
          return LatLng(c[0] as double, c[1] as double);
        }).toList();

        setState(() {
          _routePoints[emotion] = coords;
          _routeDurations[emotion] = 'Mock Min';
        });
      } else if (data['routes'] != null) {
        // Kakao API Structure
        final route = data['routes'][0];
        final List<LatLng> coords = [];
        
        for (var section in route['sections']) {
          for (var road in section['roads']) {
            for (var i = 0; i < road['vertexes'].length; i += 2) {
              coords.add(LatLng(road['vertexes'][i + 1], road['vertexes'][i]));
            }
          }
        }

        final durationSec = route['summary']['duration'] as int;
        final minutes = (durationSec / 60).round();

        setState(() {
          _routePoints[emotion] = coords;
          _routeDurations[emotion] = '$minutes min';
        });
      }
    } catch (e) {
      print('Error fetching route: $e');
    }
  }

  void _fitMapToRoute() {
    final points = _routePoints[_routeOptions[_selectedIndex].emotion] ?? [];
    if (points.isEmpty) return;

    double minLat = points.first.latitude;
    double maxLat = points.first.latitude;
    double minLon = points.first.longitude;
    double maxLon = points.first.longitude;

    for (final p in points) {
      if (p.latitude < minLat) minLat = p.latitude;
      if (p.latitude > maxLat) maxLat = p.latitude;
      if (p.longitude < minLon) minLon = p.longitude;
      if (p.longitude > maxLon) maxLon = p.longitude;
    }

    final bounds = LatLngBounds(
      LatLng(minLat, minLon),
      LatLng(maxLat, maxLon),
    );

    _mapController.fitCamera(
      CameraFit.bounds(
        bounds: bounds,
        padding: const EdgeInsets.all(60),
      ),
    );
  }

  void _selectDestination(Map<String, dynamic> result) {
    setState(() {
      _destination = LatLng(result['lat'] as double, result['lon'] as double);
      _destinationName = result['name'] as String;
      _searchResults = [];
      _showSearch = false;
      _searchController.text = _destinationName;
    });

    _fetchAllRoutes();
  }

  // ── Build ──────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return ScreenFrame(
      title: 'Mood Route',
      subtitle: 'Maps',
      child: Column(
        children: [
          _buildSearchBar(),
          const SizedBox(height: 10),
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Stack(
                children: [
                  _buildMap(),
                  if (_loadingLocation)
                    const Center(child: CircularProgressIndicator()),
                  if (_loadingRoute)
                    Positioned(
                      top: 12,
                      right: 12,
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
                              width: 12,
                              height: 12,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            ),
                            SizedBox(width: 8),
                            Text('Syncing with Backend...',
                                style: TextStyle(fontSize: 11, color: Colors.white)),
                          ],
                        ),
                      ),
                    ),
                  Positioned(
                    bottom: 12,
                    right: 12,
                    child: FloatingActionButton.small(
                      onPressed: () {
                        if (_currentLocation != null) {
                          _mapController.move(_currentLocation!, 15);
                        }
                      },
                      backgroundColor: const Color(0xFF1C232B),
                      child: const Icon(Icons.my_location, size: 20),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),
          if (_showSearch && _searchResults.isNotEmpty) _buildSearchResults(),
          if (_destination != null) _buildRouteTiles(),
        ],
      ),
    );
  }

  Widget _buildSearchBar() {
    return TextField(
      controller: _searchController,
      style: const TextStyle(color: Colors.white, fontSize: 14),
      decoration: InputDecoration(
        hintText: 'Where do you want to go?',
        hintStyle: const TextStyle(color: Colors.white38, fontSize: 14),
        prefixIcon: const Icon(Icons.search, color: Colors.white54, size: 20),
        suffixIcon: _searchController.text.isNotEmpty
            ? IconButton(
                icon: const Icon(Icons.clear, color: Colors.white38, size: 18),
                onPressed: () {
                  _searchController.clear();
                  setState(() {
                    _searchResults = [];
                    _showSearch = false;
                    _destination = null;
                    _destinationName = '';
                    _routePoints.clear();
                    _routeDurations.clear();
                  });
                },
              )
            : null,
        filled: true,
        fillColor: const Color(0xFF1C232B),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Color(0xFF00A896), width: 1.5),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      ),
      onTap: () => setState(() => _showSearch = true),
      onChanged: _searchPlaces,
    );
  }

  Widget _buildSearchResults() {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF1C232B),
        borderRadius: BorderRadius.circular(8),
      ),
      child: _searchingPlace
          ? const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
            )
          : ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: _searchResults.length,
              separatorBuilder: (_, __) => const Divider(
                height: 1,
                color: Colors.white12,
              ),
              itemBuilder: (context, i) {
                final r = _searchResults[i];
                return ListTile(
                  dense: true,
                  leading: const Icon(Icons.location_on, color: Color(0xFF00A896), size: 18),
                  title: Text(
                    r['name'] as String,
                    style: const TextStyle(color: Colors.white, fontSize: 12),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  onTap: () => _selectDestination(r),
                );
              },
            ),
    );
  }

  Widget _buildMap() {
    final selectedEmotion = _routeOptions[_selectedIndex].emotion;
    final selectedColor = _routeOptions[_selectedIndex].color;

    return FlutterMap(
      mapController: _mapController,
      options: MapOptions(
        initialCenter: _currentLocation ?? const LatLng(37.5665, 126.9780),
        initialZoom: 13,
        onTap: (_, __) {
          setState(() {
            _showSearch = false;
            _searchResults = [];
          });
        },
      ),
      children: [
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'com.example.adams_mobile',
        ),
        for (var i = 0; i < _routeOptions.length; i++)
          if (i != _selectedIndex && _routePoints[_routeOptions[i].emotion] != null)
            PolylineLayer(
              polylines: [
                Polyline(
                  points: _routePoints[_routeOptions[i].emotion]!,
                  strokeWidth: 3,
                  color: _routeOptions[i].color.withOpacity(0.25),
                ),
              ],
            ),
        if (_routePoints[selectedEmotion] != null)
          PolylineLayer(
            polylines: [
              Polyline(
                points: _routePoints[selectedEmotion]!,
                strokeWidth: 5,
                color: selectedColor,
              ),
            ],
          ),
        MarkerLayer(
          markers: [
            if (_currentLocation != null)
              Marker(
                point: _currentLocation!,
                width: 40,
                height: 40,
                child: Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFF00A896),
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white, width: 3),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF00A896).withOpacity(0.5),
                        blurRadius: 8,
                      ),
                    ],
                  ),
                  child: const Icon(Icons.navigation, size: 18, color: Colors.white),
                ),
              ),
            if (_destination != null)
              Marker(
                point: _destination!,
                width: 40,
                height: 50,
                child: Column(
                  children: [
                    Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        color: selectedColor,
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 2),
                        boxShadow: [
                          BoxShadow(
                            color: selectedColor.withOpacity(0.5),
                            blurRadius: 8,
                          ),
                        ],
                      ),
                      child: const Icon(Icons.flag, size: 16, color: Colors.white),
                    ),
                    Container(
                      width: 2,
                      height: 12,
                      color: selectedColor,
                    ),
                  ],
                ),
              ),
          ],
        ),
      ],
    );
  }

  Widget _buildRouteTiles() {
    return Column(
      children: [
        for (var i = 0; i < _routeOptions.length; i++) ...[
          if (i > 0) const SizedBox(height: 10),
          _RouteTile(
            route: _routeOptions[i],
            duration: _routeDurations[_routeOptions[i].emotion] ?? '...',
            isSelected: i == _selectedIndex,
            onTap: () {
              setState(() => _selectedIndex = i);
              _fitMapToRoute();
            },
          ),
        ],
      ],
    );
  }
}

class _RouteTile extends StatelessWidget {
  const _RouteTile({
    required this.route,
    required this.duration,
    required this.isSelected,
    required this.onTap,
  });

  final RouteOption route;
  final String duration;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 58,
      width: double.infinity,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(8),
          border: isSelected
              ? Border.all(color: route.color, width: 1.5)
              : Border.all(color: Colors.transparent),
        ),
        child: FilledButton.tonal(
          onPressed: onTap,
          style: FilledButton.styleFrom(
            backgroundColor: isSelected ? route.color.withOpacity(0.18) : null,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
          ),
          child: Row(
            children: [
              Icon(route.icon, color: isSelected ? route.color : null),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      route.label,
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        color: isSelected ? route.color : null,
                        letterSpacing: 0,
                      ),
                    ),
                    Text(
                      route.description,
                      style: const TextStyle(
                        fontSize: 11,
                        color: Colors.white54,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ),
              Text(
                duration,
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: isSelected ? route.color : Colors.white70,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
