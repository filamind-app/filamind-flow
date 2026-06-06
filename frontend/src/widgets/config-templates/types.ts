/** A ready-to-paste Klipper config / macro template (from `/api/reference/templates`). */
export interface ConfigTemplate {
  id: string
  name: string
  category: string
  description: string
  required_sections: string[]
  body: string
}
