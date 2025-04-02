import { Link } from 'react-router-dom';

export default function Home() {
  return (
    <div className="pt-16">
      {/* Hero Section */}
      <div className="bg-blue-900 text-white py-20">
        <div className="max-w-4xl mx-auto text-center px-4">
          <h1 className="text-4xl md:text-5xl font-bold mb-6">AI-Powered Research Platform for Better Insights</h1>
          <p className="text-xl mb-8">
            Accelerate your research with our advanced AI tools. Discover, analyze, and generate insights from academic papers faster than ever.
          </p>
          <div className="flex justify-center space-x-4">
            <Link 
              to="/signup" 
              className="px-6 py-3 bg-white text-blue-700 rounded-lg font-medium hover:bg-gray-100"
            >
              Get started
            </Link>
            <Link 
              to="/features" 
              className="px-6 py-3 border border-white text-white rounded-lg font-medium hover:bg-white hover:text-blue-700"
            >
              Learn more
            </Link>
          </div>
        </div>
      </div>

      {/* Features Section */}
      <div className="py-16 bg-white">
        <div className="max-w-6xl mx-auto px-4">
          <h2 className="text-3xl font-bold text-center mb-12">Powerful Research Features</h2>
          <p className="text-center text-gray-600 mb-12 max-w-3xl mx-auto">
            All the tools you need to accelerate your research workflow
          </p>
          
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                title: "AI Analysis",
                description: "Get AI-powered summaries and insights from complex research papers"
              },
              {
                title: "Semantic Search",
                description: "Find relevant research using natural language queries"
              },
              {
                title: "Research Trends",
                description: "Visualize emerging trends and patterns across academic fields"
              }
            ].map((feature, index) => (
              <div key={index} className="bg-gray-50 p-6 rounded-lg">
                <h3 className="text-xl font-semibold mb-3">{feature.title}</h3>
                <p className="text-gray-600">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* How It Works */}
      <div className="py-16 bg-gray-50">
        <div className="max-w-6xl mx-auto px-4">
          <h2 className="text-3xl font-bold text-center mb-12">How It Works</h2>
          <p className="text-center text-gray-600 mb-12 max-w-3xl mx-auto">
            Our platform is designed to simplify your research workflow
          </p>
          
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                step: "01",
                title: "Ask questions",
                description: "Type your research question or upload a document to analyze"
              },
              {
                step: "02",
                title: "Get AI analysis",
                description: "Our AI processes your query and searches across millions of papers"
              },
              {
                step: "03",
                title: "Review insights",
                description: "Receive summaries, key points, and connections to explore"
              }
            ].map((item, index) => (
              <div key={index} className="bg-white p-6 rounded-lg shadow-sm">
                <div className="text-2xl font-bold text-blue-900 mb-3">{item.step}</div>
                <h3 className="text-xl font-semibold mb-3">{item.title}</h3>
                <p className="text-gray-600">{item.description}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CTA Section */}
      <div className="py-16 bg-blue-900 text-white">
        <div className="max-w-4xl mx-auto text-center px-4">
          <h2 className="text-3xl font-bold mb-6">Ready to enhance your research?</h2>
          <p className="text-xl mb-8">
            Join thousands of researchers using our platform
          </p>
          <Link 
            to="/signup" 
            className="inline-block px-8 py-3 bg-white text-blue-700 rounded-lg font-medium hover:bg-gray-100"
          >
            Get Started
          </Link>
        </div>
      </div>
    </div>
  );
}