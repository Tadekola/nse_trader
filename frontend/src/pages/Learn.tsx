/**
 * Learn Page - Educational Content Hub
 * 
 * Provides educational content for investors at all levels.
 * Features articles, lessons, and learning paths.
 */

import React from 'react';
import { EmptyState } from '../core';

interface LearningTopic {
  id: string;
  title: string;
  description: string;
  level: 'beginner' | 'intermediate' | 'advanced';
  category: string;
  readTime: number;
}

const LEARNING_TOPICS: LearningTopic[] = [
  {
    id: '1',
    title: 'Understanding the Nigerian Stock Exchange',
    description: 'An introduction to the NGX, how it works, and why it matters for your investments.',
    level: 'beginner',
    category: 'Fundamentals',
    readTime: 8,
  },
  {
    id: '2', 
    title: 'Reading Stock Charts',
    description: 'Learn to interpret price charts, identify trends, and spot key patterns.',
    level: 'beginner',
    category: 'Technical Analysis',
    readTime: 12,
  },
  {
    id: '3',
    title: 'Understanding Market Breadth',
    description: 'How to use advancers vs decliners to gauge overall market health.',
    level: 'intermediate',
    category: 'Market Analysis',
    readTime: 6,
  },
  {
    id: '4',
    title: 'Liquidity in Nigerian Stocks',
    description: 'Why liquidity matters and how to avoid getting stuck in illiquid positions.',
    level: 'beginner',
    category: 'Risk Management',
    readTime: 7,
  },
  {
    id: '5',
    title: 'Position Sizing Strategies',
    description: 'How much to invest in each trade based on your risk tolerance and account size.',
    level: 'intermediate',
    category: 'Risk Management',
    readTime: 10,
  },
  {
    id: '6',
    title: 'Understanding P/E Ratios',
    description: 'How to use price-to-earnings ratios to evaluate Nigerian stocks.',
    level: 'beginner',
    category: 'Fundamentals',
    readTime: 5,
  },
];

const levelColors = {
  beginner: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  intermediate: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  advanced: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
};

const Learn: React.FC = () => {
  const [selectedLevel, setSelectedLevel] = React.useState<string>('all');
  const [selectedCategory, setSelectedCategory] = React.useState<string>('all');

  const categories = ['all', ...new Set(LEARNING_TOPICS.map(t => t.category))];
  
  const filteredTopics = LEARNING_TOPICS.filter(topic => {
    if (selectedLevel !== 'all' && topic.level !== selectedLevel) return false;
    if (selectedCategory !== 'all' && topic.category !== selectedCategory) return false;
    return true;
  });

  return (
    <div className="space-y-6 pb-8">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">
          Learn
        </h1>
        <p className="text-sm text-[var(--color-text-tertiary)] mt-1">
          Build your investing knowledge with curated educational content
        </p>
      </div>

      {/* Filters */}
      <div className="card p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Level Filter */}
          <div>
            <label className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide block mb-2">
              Level
            </label>
            <div className="flex items-center gap-1 p-1 bg-[var(--color-bg-tertiary)] rounded-lg">
              {['all', 'beginner', 'intermediate', 'advanced'].map((level) => (
                <button
                  key={level}
                  onClick={() => setSelectedLevel(level)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                    selectedLevel === level
                      ? 'bg-[var(--color-accent-primary)] text-white'
                      : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
                  }`}
                >
                  {level === 'all' ? 'All Levels' : level.charAt(0).toUpperCase() + level.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Category Filter */}
          <div>
            <label className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide block mb-2">
              Category
            </label>
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="px-3 py-2 bg-[var(--color-bg-tertiary)] border border-[var(--color-border-subtle)] rounded-lg text-sm text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent-primary)]"
            >
              {categories.map(cat => (
                <option key={cat} value={cat}>
                  {cat === 'all' ? 'All Categories' : cat}
                </option>
              ))}
            </select>
          </div>

          {/* Results count */}
          <span className="text-xs text-[var(--color-text-tertiary)] ml-auto">
            {filteredTopics.length} topics
          </span>
        </div>
      </div>

      {/* Topics Grid */}
      {filteredTopics.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredTopics.map(topic => (
            <button
              key={topic.id}
              className="card p-4 text-left hover:bg-[var(--color-bg-hover)] transition-colors group"
            >
              <div className="flex items-start justify-between mb-3">
                <span className={`px-2 py-0.5 text-xs font-medium rounded border ${levelColors[topic.level]}`}>
                  {topic.level}
                </span>
                <span className="text-xs text-[var(--color-text-tertiary)]">
                  {topic.readTime} min read
                </span>
              </div>

              <h3 className="font-medium text-[var(--color-text-primary)] group-hover:text-[var(--color-accent-primary)] transition-colors mb-2">
                {topic.title}
              </h3>
              
              <p className="text-sm text-[var(--color-text-tertiary)] line-clamp-2">
                {topic.description}
              </p>

              <div className="mt-3 flex items-center justify-between">
                <span className="text-xs text-[var(--color-text-tertiary)]">{topic.category}</span>
                <svg width="16" height="16" className="w-4 h-4 text-[var(--color-text-tertiary)] group-hover:text-[var(--color-accent-primary)] transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </button>
          ))}
        </div>
      ) : (
        <div className="card">
          <EmptyState
            variant="search"
            title="No topics match your filters"
            description="Try adjusting your level or category filters."
            action={{
              label: 'Clear filters',
              onClick: () => {
                setSelectedLevel('all');
                setSelectedCategory('all');
              },
            }}
          />
        </div>
      )}

      {/* Coming Soon Section */}
      <div className="card p-6 border-l-4 border-l-[var(--color-accent-primary)]">
        <h3 className="font-medium text-[var(--color-text-primary)] mb-2">
          More Content Coming Soon
        </h3>
        <p className="text-sm text-[var(--color-text-tertiary)]">
          We're building out a comprehensive learning library with video tutorials, 
          interactive quizzes, and Nigerian market case studies. Check back regularly for updates.
        </p>
      </div>
    </div>
  );
};

export default Learn;
