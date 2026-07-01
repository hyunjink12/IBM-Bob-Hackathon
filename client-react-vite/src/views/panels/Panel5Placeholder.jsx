/**
 * Panel 5 placeholder until content is defined.
 */
export function Panel5Placeholder({ panel5 }) {
  return (
    <section className="panel panel--placeholder">
      <header className="panel__header">
        <h2>Panel 5</h2>
        <span className="panel__meta">{panel5?.status ?? 'placeholder'}</span>
      </header>
      <p>{panel5?.message ?? 'Reserved for RBOB blending context or WASDE deep-dive.'}</p>
    </section>
  )
}
