<script lang="ts">
	import { onMount } from 'svelte';
	import { invalidateAll } from '$app/navigation';
	import { toast } from '$lib/stores/toast';
	import { getProfile, patchProfile, type UserProfile } from '$lib/api/profile';
	import { Save, Loader, User, Sparkles } from '@lucide/svelte';

	import ProfilePictureSection from '$lib/components/profile/ProfilePictureSection.svelte';
	import PersonalInfoSection from '$lib/components/profile/PersonalInfoSection.svelte';
	import AddressInfoSection from '$lib/components/profile/AddressInfoSection.svelte';
	import LocationSection from '$lib/components/profile/LocationSection.svelte';
	import ProfessionalInfoSection from '$lib/components/profile/ProfessionalInfoSection.svelte';
	import AccountSecuritySection from '$lib/components/profile/AccountSecuritySection.svelte';

	let profile: UserProfile | null = null;
	let loading = true;
	let saving = false;
	let validationErrors: Record<string, string> = {};

	let formData = {
		first_name: '',
		last_name: '',
		mobile: '',
		alternate_mobile: '',
		gender: '',
		dob: '',
		marital_status: '',
		nationality: '',
		address: '',
		permanent_address: '',
		pincode: '',
		city_id: undefined as number | undefined,
		state_id: undefined as number | undefined,
		country_id: undefined as number | undefined,
		current_city_id: undefined as number | undefined,
		preferred_city_ids: [] as number[],
		job_role: '',
		profile_description: '',
		year: '',
		month: '',
		current_salary: '',
		expected_salary: '',
		notice_period: '',
		relocation: false
	};

	onMount(async () => {
		await loadProfile();
	});

	async function loadProfile() {
		try {
			loading = true;
			profile = await getProfile();

			formData = {
				first_name: profile.first_name || '',
				last_name: profile.last_name || '',
				mobile: profile.mobile || '',
				alternate_mobile: profile.alternate_mobile?.toString() || '',
				gender: profile.gender || '',
				dob: profile.dob || '',
				marital_status: profile.marital_status || '',
				nationality: profile.nationality || '',
				address: profile.address || '',
				permanent_address: profile.permanent_address || '',
				pincode: profile.pincode?.toString() || '',
				city_id: profile.city?.id,
				state_id: profile.state?.id,
				country_id: profile.country?.id,
				current_city_id: profile.current_city?.id,
				preferred_city_ids: profile.preferred_city?.map((c) => c.id) || [],
				job_role: profile.job_role || '',
				profile_description: profile.profile_description || '',
				year: profile.year || '',
				month: profile.month || '',
				current_salary: profile.current_salary || '',
				expected_salary: profile.expected_salary || '',
				notice_period: profile.notice_period || '',
				relocation: profile.relocation || false
			};
		} catch (err) {
			const errorMessage = err instanceof Error ? err.message : 'Failed to load profile';
			toast.error(errorMessage);
			console.error('Profile load error:', err);
		} finally {
			loading = false;
		}
	}

	async function handleSaveProfile() {
		try {
			saving = true;
			validationErrors = {};

			if (!formData.first_name.trim()) {
				validationErrors.first_name = 'First name is required';
			}
			if (!formData.last_name.trim()) {
				validationErrors.last_name = 'Last name is required';
			}
			if (formData.mobile && !/^\+?[\d\s\-()]+$/.test(formData.mobile)) {
				validationErrors.mobile = 'Invalid phone number format';
			}
			if (formData.alternate_mobile && !/^\+?[\d\s\-().]+$/.test(formData.alternate_mobile)) {
				validationErrors.alternate_mobile = 'Invalid phone number format';
			}
			if (formData.pincode && !/^[A-Za-z0-9](?:[A-Za-z0-9 -]{0,8}[A-Za-z0-9])?$/.test(formData.pincode.trim())) {
				validationErrors.pincode = 'Enter a valid postcode (up to 10 letters or digits)';
			}

			if (Object.keys(validationErrors).length > 0) {
				saving = false;
				return;
			}

			// Send every field, including emptied ones, so clearing an input
			// actually clears it: text fields go as '' and dates, numbers and
			// ids as null. Skipping empty values left the old value in place
			// while the page still reported success.
			const text = (value: string | number | null | undefined) => String(value ?? '').trim();

			const updatePayload: Record<string, unknown> = {
				first_name: text(formData.first_name),
				last_name: text(formData.last_name),
				mobile: text(formData.mobile),
				// Phone numbers and postcodes stay text: a leading 0 or + is part of the value.
				alternate_mobile: text(formData.alternate_mobile) || null,
				gender: formData.gender || '',
				dob: formData.dob || null,
				marital_status: formData.marital_status || '',
				nationality: text(formData.nationality),
				address: text(formData.address),
				permanent_address: text(formData.permanent_address),
				pincode: text(formData.pincode) || null,
				city_id: formData.city_id || null,
				state_id: formData.state_id || null,
				country_id: formData.country_id || null,
				current_city_id: formData.current_city_id || null,
				preferred_city_ids: formData.preferred_city_ids ?? [],
				job_role: text(formData.job_role),
				profile_description: text(formData.profile_description),
				year: text(formData.year),
				month: text(formData.month),
				current_salary: text(formData.current_salary),
				expected_salary: text(formData.expected_salary),
				notice_period: text(formData.notice_period),
				relocation: formData.relocation
			};

			profile = await patchProfile(updatePayload);

			// The header reads the user from the server-loaded layout data, so
			// re-run the loads rather than mutating a client-side copy.
			await invalidateAll();

			toast.success('Profile updated successfully!');
		} catch (err) {
			const errorMessage = err instanceof Error ? err.message : 'Failed to update profile';
			toast.error(errorMessage);
			console.error('Profile update error:', err);
		} finally {
			saving = false;
		}
	}
</script>

<svelte:head>
	<title>Personal Information - Profile - PeelJobs</title>
	<meta name="description" content="Manage your personal information and preferences" />
</svelte:head>

<!-- Header -->
<div class="mb-6 animate-fade-in-up" style="opacity: 0; animation-fill-mode: forwards;">
	<div class="flex items-center gap-3 mb-2">
		<div class="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
			<User size={20} class="text-primary" />
		</div>
		<div>
			<h2 class="text-xl lg:text-2xl font-semibold text-black">Personal Information</h2>
			<p class="text-sm text-muted">Manage your personal information and preferences</p>
		</div>
	</div>
</div>

<!-- Loading State -->
{#if loading}
	<div
		class="bg-white rounded-lg p-12 shadow-sm border border-border text-center animate-fade-in-up"
		style="opacity: 0; animation-delay: 100ms; animation-fill-mode: forwards;"
	>
		<div
			class="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4"
		></div>
		<p class="text-muted">Loading your profile...</p>
	</div>
{:else if profile}
	<!-- Profile Completion Card -->
	{#if profile.profile_completion_percentage < 100}
		<div
			class="bg-white rounded-lg p-5 lg:p-6 shadow-sm border border-border mb-6 animate-fade-in-up"
			style="opacity: 0; animation-delay: 100ms; animation-fill-mode: forwards;"
		>
			<div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
				<div class="flex items-start gap-4">
					<div
						class="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0"
					>
						<Sparkles size={24} class="text-primary" />
					</div>
					<div>
						<h3 class="text-lg font-semibold text-black mb-1">Complete Your Profile</h3>
						<p class="text-sm text-muted">
							A complete profile gets 3x more views from recruiters
						</p>
					</div>
				</div>

				<div class="flex items-center gap-4 lg:gap-6">
					<div class="flex-1 lg:w-48">
						<div class="flex justify-between text-sm mb-2">
							<span class="text-muted">Progress</span>
							<span class="font-semibold text-primary"
								>{profile.profile_completion_percentage}%</span
							>
						</div>
						<div class="w-full bg-surface rounded-full h-2.5">
							<div
								class="bg-primary rounded-full h-2.5 transition-all duration-500"
								style="width: {profile.profile_completion_percentage}%"
							></div>
						</div>
					</div>
				</div>
			</div>
		</div>
	{/if}

	<!-- Profile Form -->
	<form
		onsubmit={(e) => {
			e.preventDefault();
			handleSaveProfile();
		}}
		class="space-y-6"
	>
		<!-- Profile Picture Section -->
		<div
			class="bg-white rounded-lg shadow-sm border border-border overflow-hidden animate-fade-in-up"
			style="opacity: 0; animation-delay: 150ms; animation-fill-mode: forwards;"
		>
			<ProfilePictureSection
				profilePicUrl={profile.profile_pic_url}
				photo={profile.photo}
				onUploadComplete={loadProfile}
			/>
		</div>

		<!-- Personal Information Section -->
		<div
			class="bg-white rounded-lg shadow-sm border border-border overflow-hidden animate-fade-in-up"
			style="opacity: 0; animation-delay: 200ms; animation-fill-mode: forwards;"
		>
			<PersonalInfoSection bind:formData email={profile.email} {validationErrors} />
		</div>

		<!-- Address Information Section -->
		<div
			class="bg-white rounded-lg shadow-sm border border-border overflow-hidden animate-fade-in-up"
			style="opacity: 0; animation-delay: 250ms; animation-fill-mode: forwards;"
		>
			<AddressInfoSection bind:formData {validationErrors} />
		</div>

		<!-- Location Preferences Section -->
		<div
			class="bg-white rounded-lg shadow-sm border border-border overflow-hidden animate-fade-in-up"
			style="opacity: 0; animation-delay: 300ms; animation-fill-mode: forwards;"
		>
			<LocationSection bind:formData {profile} />
		</div>

		<!-- Professional Information Section -->
		<div
			class="bg-white rounded-lg shadow-sm border border-border overflow-hidden animate-fade-in-up"
			style="opacity: 0; animation-delay: 350ms; animation-fill-mode: forwards;"
		>
			<ProfessionalInfoSection bind:formData />
		</div>

		<!-- Save Button -->
		<div
			class="flex justify-end gap-4 animate-fade-in-up"
			style="opacity: 0; animation-delay: 400ms; animation-fill-mode: forwards;"
		>
			<button
				type="submit"
				disabled={saving}
				class="px-6 py-3 bg-primary text-white rounded-full font-medium hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-sm"
			>
				{#if saving}
					<Loader size={20} class="animate-spin" />
					Saving...
				{:else}
					<Save size={20} />
					Save Profile
				{/if}
			</button>
		</div>
	</form>

	<!--
		Outside the profile <form> on purpose: this section posts to its own
		endpoints (change-email / change-password) and nested forms are invalid
		HTML — inside, its submit buttons would trigger the profile save.
	-->
	<div
		class="bg-white rounded-lg shadow-sm border border-border overflow-hidden animate-fade-in-up mt-6"
		style="opacity: 0; animation-delay: 450ms; animation-fill-mode: forwards;"
	>
		<AccountSecuritySection email={profile.email} pendingEmail={profile.pending_email ?? ''} />
	</div>
{/if}
