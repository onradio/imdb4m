#!/usr/bin/env python3
"""
QA Evaluator - Visual inspection tool for TTL extraction evaluation.

Opens saved IMDB HTML pages in a browser, highlights TTL answers with a
subtle blue box, automatically scrolls to matches, and provides navigation
to cycle through multiple matches. Includes a GUI for yes/no evaluation.
"""

import json
import os
import re
import webbrowser
from pathlib import Path
from flask import Flask, send_file, jsonify, request, Response
from bs4 import BeautifulSoup

# Paths
SCRIPT_DIR = Path(__file__).parent
QA_RESULTS_PATH = SCRIPT_DIR / "qa_results.json"

app = Flask(__name__)

# Load QA results
def load_qa_results():
    with open(QA_RESULTS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_qa_results(data):
    with open(QA_RESULTS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Get list of movies
def get_movies():
    qa_results = load_qa_results()
    return sorted(qa_results.keys())

# Questions list
QUESTIONS = [
    "Who directed the movie?",
    "Who wrote the script for the movie?",
    "Who are the actors of the movie?",
    "What is the rating of the movie?",
    "How many people have rated the movie?",
    "What is the plot of the movie?",
    "When was the movie released?",
    "What is the runtime of the movie?",
    "What is the Metacritic Score of the movie?",
    "What are the keywords associated with the movie?",
    "What is the budget of the movie?",
    "What is the trailer of the movie?",
    "What is the genre of the movie?",
    "What is the poster of the movie?",
    "Which are the production companies of the movie?",
    "What are alternate names of the movie?",
    "What is the content rating of the movie?",
    "Which are the images of the movie and their captions?",
]

def get_highlight_script(movie_id, question_idx):
    """Generate JavaScript to highlight TTL answers on the page."""
    qa_results = load_qa_results()
    movie_data = qa_results.get(movie_id, {})
    question = QUESTIONS[question_idx]
    question_data = movie_data.get(question, {})
    ttl_answers = question_data.get('ttl', [])
    current_eval = question_data.get('eval', None)
    
    # Flatten answers to searchable strings
    search_terms = []
    for answer in ttl_answers:
        if isinstance(answer, list):
            search_terms.extend([str(a) for a in answer if a])
        elif answer:
            # For comma-separated keywords, split them
            if ',' in str(answer):
                search_terms.extend([s.strip() for s in str(answer).split(',')])
            else:
                search_terms.append(str(answer))
    
    # Remove URLs and very long strings from search (they won't be visible text)
    search_terms = [t for t in search_terms if t and len(t) < 200 and not t.startswith('http')]
    
    # Escape for JavaScript
    search_terms_json = json.dumps(search_terms)
    
    return f'''
    <script>
    (function() {{
        const searchTerms = {search_terms_json};
        const questionIdx = {question_idx};
        const totalQuestions = {len(QUESTIONS)};
        const movieId = "{movie_id}";
        const question = {json.dumps(question)};
        const currentEval = {json.dumps(current_eval)};
        const ttlAnswers = {json.dumps(ttl_answers)};
        
        // Add highlight CSS to the page - subtle blue box
        const style = document.createElement('style');
        style.textContent = `
            .ttl-highlight {{
                outline: 3px solid #2196F3 !important;
                outline-offset: 2px !important;
                background: rgba(33, 150, 243, 0.1) !important;
                border-radius: 4px !important;
                display: inline !important;
                position: relative !important;
            }}
            .ttl-highlight::before {{
                content: '▼';
                position: absolute;
                top: -20px;
                left: 50%;
                transform: translateX(-50%);
                color: #2196F3;
                font-size: 14px;
                animation: bounce 0.5s ease-in-out infinite alternate;
            }}
            @keyframes bounce {{
                from {{ transform: translateX(-50%) translateY(0); }}
                to {{ transform: translateX(-50%) translateY(-5px); }}
            }}
        `;
        document.head.appendChild(style);
        
        // Store all highlights for navigation
        window.ttlHighlights = [];
        window.currentHighlightIdx = 0;
        window.highlightOverlays = [];
        
        // Create a container for overlay boxes
        const overlayContainer = document.createElement('div');
        overlayContainer.id = 'ttl-overlay-container';
        overlayContainer.style.cssText = 'position: absolute; top: 0; left: 0; pointer-events: none; z-index: 999998;';
        document.body.appendChild(overlayContainer);
        
        // Function to create overlay box at element position
        function createOverlayBox(element, idx) {{
            const rect = element.getBoundingClientRect();
            const scrollX = window.scrollX || window.pageXOffset;
            const scrollY = window.scrollY || window.pageYOffset;
            
            const overlay = document.createElement('div');
            overlay.className = 'ttl-overlay-box';
            overlay.dataset.highlightIdx = idx;
            overlay.style.cssText = `
                position: absolute;
                left: ${{rect.left + scrollX - 4}}px;
                top: ${{rect.top + scrollY - 4}}px;
                width: ${{rect.width + 8}}px;
                height: ${{rect.height + 8}}px;
                border: 3px solid #2196F3;
                border-radius: 4px;
                background: rgba(33, 150, 243, 0.15);
                pointer-events: none;
                box-sizing: border-box;
            `;
            overlayContainer.appendChild(overlay);
            return overlay;
        }}
        
        // Function to find matching elements
        function findMatchingElements(searchText) {{
            if (!searchText || searchText.length < 2) return [];
            
            const matches = [];
            const lowerSearch = searchText.toLowerCase();
            
            // Find all text-containing elements
            const elements = document.querySelectorAll('a, span, p, div, h1, h2, h3, h4, h5, h6, li, td, th, label');
            
            elements.forEach(el => {{
                // Skip if element is in the eval panel
                if (el.closest('.eval-panel') || el.closest('#ttl-overlay-container')) return;
                
                // Get direct text content only (not from children)
                let directText = '';
                Array.from(el.childNodes).forEach(node => {{
                    if (node.nodeType === Node.TEXT_NODE) {{
                        directText += node.textContent;
                    }}
                }});
                
                // Check if this element's text contains the search term
                if (directText.toLowerCase().includes(lowerSearch)) {{
                    // Check if element is visible
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {{
                        matches.push(el);
                    }}
                }}
            }});
            
            return matches;
        }}
        
        // Apply highlights using overlay boxes
        function applyHighlights() {{
            // Clear existing overlays
            overlayContainer.innerHTML = '';
            window.highlightOverlays = [];
            window.ttlHighlights = [];
            
            let overlayIdx = 0;
            searchTerms.forEach(term => {{
                const matches = findMatchingElements(term);
                matches.forEach(el => {{
                    const overlay = createOverlayBox(el, overlayIdx);
                    window.highlightOverlays.push(overlay);
                    window.ttlHighlights.push({{ element: el, overlay: overlay }});
                    overlayIdx++;
                }});
            }});
            
            // Update counter in panel
            const countText = document.querySelector('.hl-count-text');
            if (countText) {{
                countText.textContent = 'Found ' + window.ttlHighlights.length + ' highlight(s) on page';
            }}
            const counter = document.querySelector('.highlight-counter');
            if (counter && window.ttlHighlights.length > 0) {{
                counter.style.display = 'inline';
                counter.textContent = '1 / ' + window.ttlHighlights.length;
            }}
            
            return window.ttlHighlights.length;
        }}
        
        // Scroll to highlight function
        window.scrollToHighlight = function(idx) {{
            if (window.ttlHighlights.length === 0) return;
            
            // Clamp index
            if (idx < 0) idx = window.ttlHighlights.length - 1;
            if (idx >= window.ttlHighlights.length) idx = 0;
            
            window.currentHighlightIdx = idx;
            
            const item = window.ttlHighlights[idx];
            item.element.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            
            // Flash effect on the overlay
            window.highlightOverlays.forEach((ov, i) => {{
                if (i === idx) {{
                    ov.style.borderColor = '#FF5722';
                    ov.style.background = 'rgba(255, 87, 34, 0.25)';
                    ov.style.borderWidth = '4px';
                }} else {{
                    ov.style.borderColor = '#2196F3';
                    ov.style.background = 'rgba(33, 150, 243, 0.15)';
                    ov.style.borderWidth = '3px';
                }}
            }});
            
            // Update counter in panel
            const counter = document.querySelector('.highlight-counter');
            if (counter) {{
                counter.textContent = (idx + 1) + ' / ' + window.ttlHighlights.length;
            }}
        }};
        
        // Update overlay positions (call on scroll/resize)
        function updateOverlayPositions() {{
            window.ttlHighlights.forEach((item, idx) => {{
                const rect = item.element.getBoundingClientRect();
                const scrollX = window.scrollX || window.pageXOffset;
                const scrollY = window.scrollY || window.pageYOffset;
                
                item.overlay.style.left = (rect.left + scrollX - 4) + 'px';
                item.overlay.style.top = (rect.top + scrollY - 4) + 'px';
                item.overlay.style.width = (rect.width + 8) + 'px';
                item.overlay.style.height = (rect.height + 8) + 'px';
            }});
        }}
        
        // Initial highlight application with delay
        let totalHighlights = 0;
        setTimeout(() => {{
            totalHighlights = applyHighlights();
            
            // Scroll to first highlight
            if (window.ttlHighlights.length > 0) {{
                setTimeout(() => window.scrollToHighlight(0), 200);
            }}
        }}, 500);
        
        // Re-apply highlights periodically to catch DOM changes
        setInterval(() => {{
            if (document.querySelectorAll('.ttl-overlay-box').length === 0) {{
                applyHighlights();
            }}
            updateOverlayPositions();
        }}, 1000);
        
        // Update positions on resize
        window.addEventListener('resize', updateOverlayPositions);
        
        // Create evaluation panel
        const panel = document.createElement('div');
        panel.className = 'eval-panel';
        panel.innerHTML = `
            <style>
                .eval-panel {{
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    width: 400px;
                    max-height: 90vh;
                    background: #1a1a2e;
                    border: 2px solid #4a4a6a;
                    border-radius: 12px;
                    padding: 20px;
                    z-index: 999999;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    color: #e0e0e0;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
                    overflow-y: auto;
                }}
                .eval-panel h3 {{
                    margin: 0 0 15px 0;
                    color: #64b5f6;
                    font-size: 14px;
                    border-bottom: 1px solid #4a4a6a;
                    padding-bottom: 10px;
                }}
                .eval-panel .movie-id {{
                    color: #81c784;
                    font-size: 12px;
                    margin-bottom: 5px;
                }}
                .eval-panel .question {{
                    font-size: 13px;
                    margin-bottom: 15px;
                    color: #fff;
                    line-height: 1.4;
                }}
                .eval-panel .progress {{
                    font-size: 11px;
                    color: #9e9e9e;
                    margin-bottom: 10px;
                }}
                .eval-panel .answers {{
                    background: #252540;
                    border-radius: 8px;
                    padding: 12px;
                    margin-bottom: 15px;
                    max-height: 200px;
                    overflow-y: auto;
                    font-size: 12px;
                }}
                .eval-panel .answers-title {{
                    color: #64b5f6;
                    font-size: 11px;
                    margin-bottom: 8px;
                    text-transform: uppercase;
                }}
                .eval-panel .answer-item {{
                    padding: 4px 8px;
                    margin: 4px 0;
                    background: #1a1a2e;
                    border-radius: 4px;
                    border-left: 3px solid #2196F3;
                }}
                .eval-panel .highlights-count {{
                    font-size: 11px;
                    color: #ffb74d;
                    margin-bottom: 10px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }}
                .eval-panel .highlight-counter {{
                    background: #2196F3;
                    color: white;
                    padding: 2px 8px;
                    border-radius: 10px;
                    font-weight: bold;
                }}
                .eval-panel .highlight-nav {{
                    display: flex;
                    gap: 8px;
                    margin-bottom: 15px;
                }}
                .eval-panel .hl-nav-btn {{
                    flex: 1;
                    padding: 8px 12px;
                    background: #2196F3;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 12px;
                    transition: background 0.2s;
                }}
                .eval-panel .hl-nav-btn:hover {{
                    background: #1976D2;
                }}
                .eval-panel .buttons {{
                    display: flex;
                    gap: 10px;
                    margin-bottom: 15px;
                }}
                .eval-panel button {{
                    flex: 1;
                    padding: 12px 20px;
                    border: none;
                    border-radius: 8px;
                    cursor: pointer;
                    font-size: 14px;
                    font-weight: 600;
                    transition: all 0.2s;
                }}
                .eval-panel .btn-yes {{
                    background: #4caf50;
                    color: white;
                }}
                .eval-panel .btn-yes:hover {{
                    background: #66bb6a;
                }}
                .eval-panel .btn-no {{
                    background: #f44336;
                    color: white;
                }}
                .eval-panel .btn-no:hover {{
                    background: #ef5350;
                }}
                .eval-panel .btn-skip {{
                    background: #757575;
                    color: white;
                }}
                .eval-panel .btn-skip:hover {{
                    background: #9e9e9e;
                }}
                .eval-panel .current-eval {{
                    font-size: 12px;
                    padding: 8px;
                    border-radius: 6px;
                    margin-bottom: 15px;
                    text-align: center;
                }}
                .eval-panel .current-eval.yes {{
                    background: rgba(76, 175, 80, 0.2);
                    color: #81c784;
                }}
                .eval-panel .current-eval.no {{
                    background: rgba(244, 67, 54, 0.2);
                    color: #e57373;
                }}
                .eval-panel .current-eval.none {{
                    background: rgba(158, 158, 158, 0.2);
                    color: #9e9e9e;
                }}
                .eval-panel .nav-buttons {{
                    display: flex;
                    gap: 10px;
                    border-top: 1px solid #4a4a6a;
                    padding-top: 15px;
                }}
                .eval-panel .nav-btn {{
                    background: #3a3a5a;
                    color: #e0e0e0;
                }}
                .eval-panel .nav-btn:hover {{
                    background: #4a4a6a;
                }}
                .eval-panel .nav-btn:disabled {{
                    opacity: 0.5;
                    cursor: not-allowed;
                }}
                .eval-panel .skip-btn {{
                    background: #ff9800;
                    color: #000;
                }}
                .eval-panel .skip-btn:hover {{
                    background: #ffb74d;
                }}
                .eval-panel .skip-btn:disabled {{
                    background: #5a5a7a;
                    color: #888;
                }}
            </style>
            <div class="movie-id">Movie: ${{movieId}}</div>
            <div class="progress">Question ${{questionIdx + 1}} of ${{totalQuestions}}</div>
            <h3>📋 Evaluation</h3>
            <div class="question">${{question}}</div>
            <div class="answers">
                <div class="answers-title">TTL Answers to find:</div>
                ${{ttlAnswers.length > 0 ? ttlAnswers.map(a => 
                    '<div class="answer-item">' + (Array.isArray(a) ? a.join(' | ') : a) + '</div>'
                ).join('') : '<div style="color: #9e9e9e;">No answers in TTL</div>'}}
            </div>
            <div class="highlights-count">
                <span class="hl-count-text">Searching for matches...</span>
                <span class="highlight-counter" style="display:none;">1 / 0</span>
            </div>
            <div class="highlight-nav">
                <button class="hl-nav-btn" onclick="scrollToHighlight(window.currentHighlightIdx - 1)">◀ Prev Match</button>
                <button class="hl-nav-btn" onclick="scrollToHighlight(window.currentHighlightIdx + 1)">Next Match ▶</button>
            </div>
            <div class="current-eval ${{currentEval === true ? 'yes' : currentEval === false ? 'no' : 'none'}}">
                Current evaluation: ${{currentEval === true ? '✓ YES' : currentEval === false ? '✗ NO' : 'Not evaluated'}}
            </div>
            <div class="buttons">
                <button class="btn-yes" onclick="submitEval(true)">✓ Yes</button>
                <button class="btn-no" onclick="submitEval(false)">✗ No</button>
                <button class="btn-skip" onclick="submitEval(null)">Skip</button>
            </div>
            <div class="nav-buttons">
                <button class="nav-btn" onclick="navigate(-1)" ${{questionIdx === 0 ? 'disabled' : ''}}>← Prev</button>
                <button class="nav-btn" onclick="navigate(1)" ${{questionIdx === totalQuestions - 1 ? 'disabled' : ''}}>Next →</button>
            </div>
            <div class="nav-buttons" style="margin-top: 8px;">
                <button class="nav-btn skip-btn" onclick="skipToNextUnevaluated()" ${{currentEval === null ? 'disabled' : ''}}>⏭ Skip to Unevaluated</button>
                <button class="nav-btn" onclick="nextMovie()">Next Movie →</button>
            </div>
        `;
        document.body.appendChild(panel);
        
        // Submit evaluation
        window.submitEval = function(value) {{
            fetch('/api/evaluate', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{
                    movie_id: movieId,
                    question: question,
                    eval: value
                }})
            }}).then(response => response.json())
              .then(data => {{
                if (data.success) {{
                    // Find next unevaluated question
                    fetch('/api/next_unevaluated/' + movieId + '/' + questionIdx)
                        .then(response => response.json())
                        .then(nextData => {{
                            if (nextData.found) {{
                                window.location.href = '/movie/' + movieId + '/' + nextData.question_idx;
                            }} else if (nextData.all_evaluated) {{
                                // All done for this movie, go to next movie
                                fetch('/api/next_movie/' + movieId)
                                    .then(response => response.json())
                                    .then(movieData => {{
                                        if (movieData.next_movie) {{
                                            fetch('/api/first_unevaluated/' + movieData.next_movie)
                                                .then(response => response.json())
                                                .then(firstData => {{
                                                    window.location.href = '/movie/' + movieData.next_movie + '/' + firstData.question_idx;
                                                }});
                                        }} else {{
                                            alert('All movies fully evaluated! 🎉');
                                        }}
                                    }});
                            }}
                        }});
                }}
            }});
        }};
        
        // Navigation (regular, doesn't skip)
        window.navigate = function(delta) {{
            const newIdx = questionIdx + delta;
            if (newIdx >= 0 && newIdx < totalQuestions) {{
                window.location.href = '/movie/' + movieId + '/' + newIdx;
            }}
        }};
        
        // Skip to next unevaluated
        window.skipToNextUnevaluated = function() {{
            fetch('/api/next_unevaluated/' + movieId + '/' + questionIdx)
                .then(response => response.json())
                .then(data => {{
                    if (data.found) {{
                        window.location.href = '/movie/' + movieId + '/' + data.question_idx;
                    }} else {{
                        alert('All questions in this movie are evaluated!');
                    }}
                }});
        }};
        
        window.nextMovie = function() {{
            fetch('/api/next_movie/' + movieId)
                .then(response => response.json())
                .then(data => {{
                    if (data.next_movie) {{
                        // Go to first unevaluated question of next movie
                        fetch('/api/first_unevaluated/' + data.next_movie)
                            .then(response => response.json())
                            .then(firstData => {{
                                window.location.href = '/movie/' + data.next_movie + '/' + firstData.question_idx;
                            }});
                    }} else {{
                        alert('This is the last movie!');
                    }}
                }});
        }};
    }})();
    </script>
    '''

@app.route('/')
def index():
    """Main page - list all movies."""
    movies = get_movies()
    qa_results = load_qa_results()
    
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>QA Evaluator</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #1a1a2e;
                color: #e0e0e0;
                padding: 40px;
                max-width: 1200px;
                margin: 0 auto;
            }
            h1 {
                color: #64b5f6;
                border-bottom: 2px solid #4a4a6a;
                padding-bottom: 20px;
            }
            .movie-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: 20px;
                margin-top: 30px;
            }
            .movie-card {
                background: #252540;
                border-radius: 12px;
                padding: 20px;
                transition: transform 0.2s, box-shadow 0.2s;
            }
            .movie-card:hover {
                transform: translateY(-4px);
                box-shadow: 0 8px 24px rgba(0,0,0,0.3);
            }
            .movie-card h3 {
                margin: 0 0 15px 0;
                color: #81c784;
            }
            .movie-card a {
                display: inline-block;
                background: #4a4a6a;
                color: #fff;
                padding: 10px 20px;
                border-radius: 6px;
                text-decoration: none;
                margin-top: 10px;
            }
            .movie-card a:hover {
                background: #64b5f6;
            }
            .progress-bar {
                background: #3a3a5a;
                border-radius: 4px;
                height: 8px;
                margin-top: 10px;
                overflow: hidden;
            }
            .progress-fill {
                height: 100%;
                border-radius: 4px;
                transition: width 0.3s;
            }
            .progress-fill.complete { background: #4caf50; }
            .progress-fill.partial { background: #ffb74d; }
            .progress-fill.none { background: #757575; }
            .stats {
                font-size: 12px;
                color: #9e9e9e;
                margin-top: 8px;
            }
        </style>
    </head>
    <body>
        <h1>🎬 QA Evaluator</h1>
        <p>Click on a movie to start evaluating the extracted data.</p>
        <div class="movie-grid">
    '''
    
    for movie_id in movies:
        movie_data = qa_results.get(movie_id, {})
        total = len(QUESTIONS)
        evaluated = sum(1 for q in QUESTIONS if movie_data.get(q, {}).get('eval') is not None)
        yes_count = sum(1 for q in QUESTIONS if movie_data.get(q, {}).get('eval') is True)
        no_count = sum(1 for q in QUESTIONS if movie_data.get(q, {}).get('eval') is False)
        
        pct = (evaluated / total * 100) if total > 0 else 0
        fill_class = 'complete' if pct == 100 else 'partial' if pct > 0 else 'none'
        
        # Find first unevaluated question
        first_uneval_idx = 0
        for idx, q in enumerate(QUESTIONS):
            if movie_data.get(q, {}).get('eval') is None:
                first_uneval_idx = idx
                break
        
        status_text = "All Complete ✓" if pct == 100 else "Start Evaluation →"
        
        html += f'''
            <div class="movie-card">
                <h3>{movie_id}</h3>
                <div class="progress-bar">
                    <div class="progress-fill {fill_class}" style="width: {pct}%"></div>
                </div>
                <div class="stats">
                    {evaluated}/{total} evaluated | ✓ {yes_count} | ✗ {no_count}
                </div>
                <a href="/movie/{movie_id}/{first_uneval_idx}">{status_text}</a>
            </div>
        '''
    
    html += '''
        </div>
    </body>
    </html>
    '''
    return html

@app.route('/movie/<movie_id>/<int:question_idx>')
def movie_page(movie_id, question_idx):
    """Serve movie HTML with highlighting script injected."""
    html_path = SCRIPT_DIR / movie_id / "movie_html" / f"{movie_id}.html"
    
    if not html_path.exists():
        return f"HTML file not found: {html_path}", 404
    
    # Read and modify HTML
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Inject highlighting script before </body>
    highlight_script = get_highlight_script(movie_id, question_idx)
    html_content = html_content.replace('</body>', f'{highlight_script}</body>')
    
    return Response(html_content, mimetype='text/html')

@app.route('/api/evaluate', methods=['POST'])
def evaluate():
    """Save evaluation for a question."""
    data = request.json
    movie_id = data.get('movie_id')
    question = data.get('question')
    eval_value = data.get('eval')
    
    qa_results = load_qa_results()
    
    if movie_id in qa_results and question in qa_results[movie_id]:
        qa_results[movie_id][question]['eval'] = eval_value
        save_qa_results(qa_results)
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Movie or question not found'})

@app.route('/api/next_movie/<current_movie>')
def next_movie(current_movie):
    """Get the next movie ID that has unevaluated questions."""
    movies = get_movies()
    qa_results = load_qa_results()
    try:
        idx = movies.index(current_movie)
        # Find next movie with unevaluated questions
        for i in range(idx + 1, len(movies)):
            movie_id = movies[i]
            movie_data = qa_results.get(movie_id, {})
            # Check if there are any unevaluated questions
            for q in QUESTIONS:
                if movie_data.get(q, {}).get('eval') is None:
                    return jsonify({'next_movie': movie_id})
        # If no unevaluated movies found, return next movie anyway
        if idx < len(movies) - 1:
            return jsonify({'next_movie': movies[idx + 1]})
    except ValueError:
        pass
    return jsonify({'next_movie': None})

@app.route('/api/first_unevaluated/<movie_id>')
def first_unevaluated(movie_id):
    """Get the index of the first unevaluated question for a movie."""
    qa_results = load_qa_results()
    movie_data = qa_results.get(movie_id, {})
    
    for idx, q in enumerate(QUESTIONS):
        if movie_data.get(q, {}).get('eval') is None:
            return jsonify({'question_idx': idx})
    
    # All evaluated, return 0
    return jsonify({'question_idx': 0})

@app.route('/api/next_unevaluated/<movie_id>/<int:current_idx>')
def next_unevaluated(movie_id, current_idx):
    """Get the index of the next unevaluated question after current_idx."""
    qa_results = load_qa_results()
    movie_data = qa_results.get(movie_id, {})
    
    # Search forward from current position
    for idx in range(current_idx + 1, len(QUESTIONS)):
        if movie_data.get(QUESTIONS[idx], {}).get('eval') is None:
            return jsonify({'question_idx': idx, 'found': True})
    
    # Search from beginning if not found
    for idx in range(0, current_idx):
        if movie_data.get(QUESTIONS[idx], {}).get('eval') is None:
            return jsonify({'question_idx': idx, 'found': True, 'wrapped': True})
    
    # All evaluated
    return jsonify({'question_idx': None, 'found': False, 'all_evaluated': True})

def main():
    print("=" * 60)
    print("QA Evaluator - Visual Inspection Tool")
    print("=" * 60)
    print()
    print("Starting server at http://localhost:5000")
    print("Opening browser...")
    print()
    print("Instructions:")
    print("  1. Click on a movie to start evaluation")
    print("  2. For each question, page auto-scrolls to TTL answers (blue box)")
    print("  3. Use Prev/Next Match buttons to cycle through multiple matches")
    print("  4. Click Yes/No to evaluate if the extraction is correct")
    print("  5. Use navigation buttons to move between questions")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    
    # Open browser
    webbrowser.open('http://localhost:5000')
    
    # Run server
    app.run(host='localhost', port=5000, debug=False)

if __name__ == '__main__':
    main()

