/** Shapes returned by the Hardware Browser endpoints (`/api/hardware*`). */

export interface HardwareItem {
  category: string
  subsection: string
  manufacturer: string
  name: string
  specs: Record<string, string>
}

export interface HardwareSearchResult {
  total: number
  count: number
  offset: number
  limit: number
  items: HardwareItem[]
}

export interface HardwareCategories {
  categories: string[]
  counts?: Record<string, number>
  total: number
}
