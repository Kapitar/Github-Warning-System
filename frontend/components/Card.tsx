export default function Card() {
  return (
    <a className="" href="https://google.com">
      <div className="hover:shadow-xl hover:shadow-indigo-500/30 p-4 px-8 bg-gray-800 text-white rounded-2xl">
        <a href="https://google.com" className="font-bold text-2xl text-blue-600 hover:underline">Repo name</a>
        <h2>Event Type: PushEvent</h2>
        <ul className="list-disc list-inside">
          <li>Summary 1</li>
          <li>Summary 2</li>
          <li>Summary 3</li>
          <li>Summary 4</li>
          <li>Summary 5</li>
        </ul>

        <p className="text-sm text-gray-500 mt-2">Pushed at: 2024-01-01 12:00:00</p>
      </div>
    </a>
  )
}
