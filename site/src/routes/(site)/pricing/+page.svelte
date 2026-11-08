<script lang="ts">
	import { Check, X, Zap, Users, TrendingUp, Shield, Clock, Heart, Award, Target, Sparkles, ArrowRight, BadgeCheck, ChevronRight, ChevronDown } from '@lucide/svelte';

	// Features included in the free plan
	const includedFeatures = [
		{ name: 'Unlimited Job Postings', icon: Zap },
		{ name: 'Search Published Graduate Resumes', icon: Users },
		{ name: 'Skill, Degree and Graduation-Year Filters', icon: Target },
		{ name: 'Application Tracking', icon: TrendingUp },
		{ name: 'Private Shortlist and Notes', icon: Heart },
		{ name: 'PDF Resume Downloads', icon: Clock },
		{ name: 'Company Profile Page', icon: BadgeCheck }
	];

	// FAQs
	const faqs = [
		{
			question: 'Is GradBridge really 100% free?',
			answer: "Yes! We never charge for job postings, candidate access, or any recruiting features. Our mission is to connect employers with the best talent in Singapore and Australia at zero cost."
		},
		{
			question: 'Are there any hidden fees or premium plans?',
			answer: "No hidden fees whatsoever. We don't have premium plans because we believe all employers deserve equal access to top talent, regardless of their budget."
		},
		{
			question: 'How is GradBridge funded?',
			answer: "GradBridge is a student project. It has no paid plans and shows no advertising."
		},
		{
			question: 'Will you start charging in the future?',
			answer: "There are no plans to charge. GradBridge is built to connect graduates and employers in Singapore and Australia."
		},
		{
			question: 'How many jobs can I post?',
			answer: "There's no limit! Post as many jobs as you need, whenever you need. We want to help you build your entire team without worrying about costs."
		},
		{
			question: 'Can I access the resume database for free?',
			answer: 'Yes. Recruiters can search every graduate who has chosen to publish a resume, filter by skills, degree and graduation year, and download the published PDF. Students decide what to publish and can withdraw it at any time.'
		},
		{
			question: 'How quickly can I start posting jobs?',
			answer: 'You can create an account and post your first job in under 5 minutes. No credit card required, no approval wait times.'
		},
		{
			question: 'What kind of support do I get?',
			answer: "Send us a message through the contact form. GradBridge does not have a dedicated support team or live chat."
		}
	];

	let openFaqIndex = $state<number | null>(null);

	function toggleFaq(index: number) {
		openFaqIndex = openFaqIndex === index ? null : index;
	}
</script>

<svelte:head>
	<title>Pricing - 100% Free Forever | GradBridge - Free Job Posting in Singapore and Australia</title>
	<meta name="description" content="Post unlimited jobs for FREE. No hidden costs, no premium plans. Search published graduate resumes and post unlimited jobs at no cost. employers hiring on GradBridge." />
	<meta property="og:title" content="100% Free Job Posting Platform - GradBridge Pricing" />
	<meta property="og:description" content="Never pay for job postings again. Unlimited free access to talent across Singapore and Australia. Post jobs, search resumes, and hire the best candidates - all for free." />
	<meta property="og:type" content="website" />
	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:title" content="100% Free Job Posting Platform - GradBridge Pricing" />
	<meta name="twitter:description" content="Unlimited job postings, resume database access, and hiring tools - all FREE forever." />
</svelte:head>

<!-- Hero Section -->
<section class="bg-[#1D2226] text-white py-16 lg:py-24 relative overflow-hidden">
	<!-- Decorative Elements -->
	<div class="absolute inset-0 overflow-hidden">
		<div class="absolute top-0 left-1/4 w-96 h-96 bg-success/20 rounded-full blur-3xl"></div>
		<div class="absolute bottom-0 right-1/4 w-80 h-80 bg-primary/10 rounded-full blur-3xl"></div>
	</div>

	<div class="max-w-7xl mx-auto px-4 lg:px-8 relative">
		<!-- Breadcrumb -->
		<nav class="mb-8" aria-label="Breadcrumb">
			<ol class="flex items-center gap-2 text-sm text-muted">
				<li>
					<a href="/" class="hover:text-white transition-colors">Home</a>
				</li>
				<li class="flex items-center gap-2">
					<ChevronRight size={14} />
					<span class="text-white font-medium">Pricing</span>
				</li>
			</ol>
		</nav>

		<div class="max-w-4xl mx-auto text-center">
			<!-- Free Badge -->
			<div class="inline-flex items-center gap-2 px-4 py-2 bg-success/20 text-success rounded-full text-sm font-medium mb-6 animate-fade-in-down" style="opacity: 0;">
				<Sparkles size={16} />
				<span>100% Free Forever</span>
			</div>

			<h1 class="text-4xl md:text-5xl lg:text-6xl font-semibold tracking-tight mb-6 animate-fade-in-up" style="opacity: 0; animation-delay: 100ms;">
				Hire the Best Talent in Singapore and Australia
				<span class="block text-success mt-2">Without Spending a Cent</span>
			</h1>

			<p class="text-lg md:text-xl text-gray-300 leading-relaxed mb-10 max-w-3xl mx-auto animate-fade-in-up" style="opacity: 0; animation-delay: 200ms;">
				Post unlimited jobs and search graduates who have published their resumes - all for <strong class="text-white">FREE</strong>.
			</p>

			<!-- CTA Buttons -->
			<div class="flex flex-col sm:flex-row gap-4 justify-center mb-10 animate-fade-in-up" style="opacity: 0; animation-delay: 300ms;">
				<a href="/employer/" class="inline-flex items-center justify-center gap-2 px-8 py-4 bg-white text-black font-medium rounded-full hover:bg-gray-100 transition-colors shadow-sm">
					Start Hiring Free
					<ArrowRight size={18} />
				</a>
				<a href="#features" class="inline-flex items-center justify-center gap-2 px-8 py-4 bg-white/10 text-white font-medium rounded-full hover:bg-white/20 transition-colors border border-white/20">
					See What's Included
				</a>
			</div>

			<!-- Trust Indicators -->
			<div class="flex flex-wrap justify-center gap-6 text-sm text-muted animate-fade-in-up" style="opacity: 0; animation-delay: 400ms;">
				<div class="flex items-center gap-2">
					<Check size={16} class="text-success" />
					<span>No Credit Card Required</span>
				</div>
				<div class="flex items-center gap-2">
					<Check size={16} class="text-success" />
					<span>No Hidden Fees</span>
				</div>
				<div class="flex items-center gap-2">
					<Check size={16} class="text-success" />
					<span>Setup in 5 Minutes</span>
				</div>
			</div>
		</div>
	</div>
</section>

<!-- Pricing Card Section -->
<section id="features" class="py-16 lg:py-24 bg-surface">
	<div class="max-w-7xl mx-auto px-4 lg:px-8">
		<div class="text-center mb-12">
			<h2 class="text-2xl lg:text-3xl font-semibold text-black tracking-tight mb-4">One Simple Plan. Everything Included.</h2>
			<p class="text-base lg:text-lg text-muted max-w-3xl mx-auto">
				No tiers, no upsells, no complicated pricing. Just one powerful platform with everything you need to hire great people.
			</p>
		</div>

		<!-- Main Pricing Card -->
		<div class="max-w-2xl mx-auto">
			<div class="bg-white rounded-lg shadow-lg overflow-hidden border-2 border-primary relative">
				<!-- Popular Badge -->
				<div class="absolute top-0 right-0 bg-primary text-white px-5 py-2 text-sm font-medium rounded-bl-lg">
					Most Popular
				</div>

				<div class="p-8 lg:p-10">
					<!-- Plan Header -->
					<div class="text-center mb-8">
						<h3 class="text-2xl lg:text-3xl font-semibold text-black mb-4">Free Forever Plan</h3>
						<div class="mb-4">
							<span class="text-6xl lg:text-7xl font-semibold text-primary">$0</span>
							<span class="text-2xl text-muted ml-2">forever</span>
						</div>
						<p class="text-muted text-lg">Everything you need to build your team. No catch.</p>
					</div>

					<!-- Features List -->
					<div class="space-y-4 mb-8">
						{#each includedFeatures as feature, i}
							{@const FeatureIcon = feature.icon}
							<div class="flex items-start gap-3 animate-fade-in-up" style="opacity: 0; animation-delay: {i * 50}ms;">
								<div class="w-6 h-6 rounded-full bg-success-light flex items-center justify-center flex-shrink-0 mt-0.5">
									<Check size={14} class="text-success" />
								</div>
								<div class="flex items-center gap-3 flex-1">
									<FeatureIcon size={18} class="text-primary flex-shrink-0" />
									<span class="text-muted font-medium">{feature.name}</span>
								</div>
							</div>
						{/each}
					</div>

					<!-- CTA Button -->
					<a href="/employer/" class="w-full flex items-center justify-center gap-2 px-8 py-4 bg-primary hover:bg-primary-hover text-white font-medium rounded-full transition-colors shadow-sm hover:shadow-md">
						Get Started Free
						<ArrowRight size={18} />
					</a>
				</div>
			</div>
		</div>
	</div>
</section>

<!-- Why Free Section -->
<section class="py-16 lg:py-24 bg-surface">
	<div class="max-w-7xl mx-auto px-4 lg:px-8">
		<div class="text-center mb-12">
			<h2 class="text-2xl lg:text-3xl font-semibold text-black tracking-tight mb-4">Why Is GradBridge Free?</h2>
			<p class="text-base lg:text-lg text-muted max-w-3xl mx-auto">
				Our mission is simple: connect employers with the best talent in Singapore and Australia without financial barriers.
			</p>
		</div>

		<div class="grid md:grid-cols-3 gap-6 max-w-6xl mx-auto">
			<div class="bg-white rounded-lg p-8 shadow-sm hover:shadow-lg transition-all border border-border">
				<div class="w-14 h-14 bg-primary/10 rounded-lg flex items-center justify-center mb-6">
					<Heart size={28} class="text-primary" />
				</div>
				<h3 class="text-xl font-semibold text-black mb-4">Our Mission</h3>
				<p class="text-muted leading-relaxed">
					We believe every company, from startups to enterprises, deserves access to top talent without budget constraints limiting their growth.
				</p>
			</div>

			<div class="bg-white rounded-lg p-8 shadow-sm hover:shadow-lg transition-all border border-border">
				<div class="w-14 h-14 bg-success-light rounded-lg flex items-center justify-center mb-6">
					<Users size={28} class="text-success" />
				</div>
				<h3 class="text-xl font-semibold text-black mb-4">More Opportunities</h3>
				<p class="text-muted leading-relaxed">
					By eliminating posting fees, we create more job opportunities for seekers and help employers find candidates they otherwise couldn't afford to reach.
				</p>
			</div>

			<div class="bg-white rounded-lg p-8 shadow-sm hover:shadow-lg transition-all border border-border">
				<div class="w-14 h-14 bg-primary/10 rounded-lg flex items-center justify-center mb-6">
					<TrendingUp size={28} class="text-primary" />
				</div>
				<h3 class="text-xl font-semibold text-black mb-4">Better Outcomes</h3>
				<p class="text-muted leading-relaxed">
					When more employers can afford to post jobs and more candidates apply, everyone wins. We measure success by successful hires, not revenue.
				</p>
			</div>
		</div>
	</div>
</section>

<!-- FAQ Section -->
<section class="py-16 lg:py-24 bg-white">
	<div class="max-w-7xl mx-auto px-4 lg:px-8">
		<div class="text-center mb-12">
			<h2 class="text-2xl lg:text-3xl font-semibold text-black tracking-tight mb-4">Frequently Asked Questions</h2>
			<p class="text-base lg:text-lg text-muted max-w-3xl mx-auto">
				Everything you need to know about our free platform
			</p>
		</div>

		<div class="max-w-3xl mx-auto space-y-3">
			{#each faqs as faq, index}
				<div class="bg-surface rounded-lg border border-border hover:border-primary/30 transition-colors overflow-hidden">
					<button onclick={() => toggleFaq(index)} class="w-full px-6 py-5 text-left flex justify-between items-center gap-4">
						<span class="font-semibold text-black text-base lg:text-lg">{faq.question}</span>
						<div class="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
							<ChevronDown size={18} class="text-primary transform transition-transform {openFaqIndex === index ? 'rotate-180' : ''}" />
						</div>
					</button>
					{#if openFaqIndex === index}
						<div class="px-6 pb-5 text-muted leading-relaxed animate-fade-in">
							{faq.answer}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	</div>
</section>

<!-- Final CTA Section -->
<section class="py-16 lg:py-24 bg-[#1D2226] text-white">
	<div class="max-w-7xl mx-auto px-4 lg:px-8 text-center">
		<div class="max-w-3xl mx-auto">
			<h2 class="text-2xl lg:text-3xl font-semibold tracking-tight mb-6">Ready to Start Hiring?</h2>
			<p class="text-lg text-gray-300 mb-10 leading-relaxed">
				Find graduates in Singapore and Australia at no cost. Create your free account in minutes and post your first job today.
			</p>

			<div class="flex flex-col sm:flex-row gap-4 justify-center mb-10">
				<a href="/employer/" class="inline-flex items-center justify-center gap-2 px-8 py-4 bg-white text-black font-medium rounded-full hover:bg-gray-100 transition-colors shadow-sm">
					Create Free Account
					<ArrowRight size={18} />
				</a>
				<a href="/contact/" class="inline-flex items-center justify-center gap-2 px-8 py-4 bg-white/10 text-white font-medium rounded-full hover:bg-white/20 transition-colors border border-white/20">
					Talk to Our Team
				</a>
			</div>

			<div class="flex flex-wrap justify-center gap-6 text-sm text-muted">
				<div class="flex items-center gap-2">
					<Check size={16} class="text-success" />
					<span>Free Forever</span>
				</div>
				<div class="flex items-center gap-2">
					<Check size={16} class="text-success" />
					<span>No Credit Card</span>
				</div>
				<div class="flex items-center gap-2">
					<Check size={16} class="text-success" />
					<span>5 Minute Setup</span>
				</div>
				<div class="flex items-center gap-2">
					<Check size={16} class="text-success" />
					<span>Unlimited Postings</span>
				</div>
			</div>
		</div>
	</div>
</section>
