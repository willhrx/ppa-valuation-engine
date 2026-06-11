import { useEffect, useRef } from 'react'
import maplibregl, { type Map as MlMap, type Marker } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

interface LocationMapProps {
  lat: number
  lon: number
  onChange: (lat: number, lon: number) => void
  height?: number
}

const OSM_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: [
        'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
        'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
        'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png',
      ],
      tileSize: 256,
      attribution:
        '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
      maxzoom: 19,
    },
  },
  layers: [
    {
      id: 'osm-tiles',
      type: 'raster',
      source: 'osm',
      minzoom: 0,
      maxzoom: 22,
    },
  ],
}

export function LocationMap({
  lat,
  lon,
  onChange,
  height = 220,
}: LocationMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MlMap | null>(null)
  const markerRef = useRef<Marker | null>(null)
  const onChangeRef = useRef(onChange)
  useEffect(() => {
    onChangeRef.current = onChange
  })

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: OSM_STYLE,
      center: [lon, lat],
      zoom: 7,
      attributionControl: { compact: true },
      cooperativeGestures: false,
    })
    mapRef.current = map

    const marker = new maplibregl.Marker({
      draggable: true,
      color: 'oklch(0.66 0.2 50)',
    })
      .setLngLat([lon, lat])
      .addTo(map)
    markerRef.current = marker

    marker.on('dragend', () => {
      const { lng, lat: nextLat } = marker.getLngLat()
      onChangeRef.current(Number(nextLat.toFixed(4)), Number(lng.toFixed(4)))
    })

    map.on('click', (event) => {
      const { lng, lat: nextLat } = event.lngLat
      marker.setLngLat([lng, nextLat])
      onChangeRef.current(Number(nextLat.toFixed(4)), Number(lng.toFixed(4)))
    })

    return () => {
      marker.remove()
      map.remove()
      mapRef.current = null
      markerRef.current = null
    }
    // Initial-mount only; subsequent prop changes go through the sync effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const marker = markerRef.current
    const map = mapRef.current
    if (!marker || !map) return
    const current = marker.getLngLat()
    if (
      Math.abs(current.lat - lat) > 1e-6 ||
      Math.abs(current.lng - lon) > 1e-6
    ) {
      marker.setLngLat([lon, lat])
      map.easeTo({ center: [lon, lat], duration: 400 })
    }
  }, [lat, lon])

  return (
    <div
      ref={containerRef}
      className="w-full overflow-hidden rounded-md border"
      style={{ height }}
    />
  )
}
