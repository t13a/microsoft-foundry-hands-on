// Fixed emergency contacts shown by show_emergency_contacts (F-AGT-30). Not written by the model.
// Keep in step with agent/content/messages.toml (content_filtered).
export const emergencyContacts = {
  title: '緊急の場合は、次の窓口にご相談ください。',
  contacts: [
    { name: '事件・事故', detail: '警察', phone: '110' },
    { name: '火事・救急', detail: '消防', phone: '119' },
    { name: '心の悩み', detail: 'こころの健康相談統一ダイヤル', phone: '0570-064-556' },
  ],
}
