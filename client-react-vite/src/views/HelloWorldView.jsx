import { useHelloWorldViewModel } from '../viewmodels/hello_world_view_model.js'

/**
 * Blank page that shows the backend hello message or an error.
 *
 * Casual: hello world if the API works, red text if not.
 */
export function HelloWorldView() {
  const { status, displayText, errorDetail } = useHelloWorldViewModel()

  if (status === 'loading') {
    return <main className="hello-page" aria-busy="true" />
  }

  if (status === 'error') {
    return (
      <main className="hello-page hello-page--error" role="alert">
        {errorDetail}
      </main>
    )
  }

  return <main className="hello-page">{displayText}</main>
}
