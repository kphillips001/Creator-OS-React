CREATE TABLE IF NOT EXISTS public.creator_world_models (
    id BIGSERIAL PRIMARY KEY,
    creator_profile_id INTEGER NOT NULL UNIQUE
        REFERENCES public.creator_profiles(id) ON DELETE CASCADE,
    fanvue_account_id TEXT NOT NULL UNIQUE,
    internal_home_base TEXT NOT NULL,
    public_location_description TEXT NOT NULL,
    home_and_indoor_environments TEXT NOT NULL,
    coastal_environments TEXT NOT NULL,
    mountains_lakes_and_small_town_escapes TEXT NOT NULL,
    climate_and_seasonal_behavior TEXT NOT NULL,
    seasonal_activities TEXT NOT NULL,
    holiday_rhythm TEXT NOT NULL,
    travel_and_variety_guidance TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.creator_world_models IS
    'Account-scoped editable Creator World Model. Not consumed by generation.';

INSERT INTO public.creator_world_models (
    creator_profile_id,
    fanvue_account_id,
    internal_home_base,
    public_location_description,
    home_and_indoor_environments,
    coastal_environments,
    mountains_lakes_and_small_town_escapes,
    climate_and_seasonal_behavior,
    seasonal_activities,
    holiday_rhythm,
    travel_and_variety_guidance
)
SELECT
    profile.id,
    profile.fanvue_account_id,
    $world$Ava’s internal home base is Wilmington, North Carolina.

Creator_OS may use this internal location to understand regional climate, seasons, coastal geography, vegetation, and believable local activities.

The internal home base must not automatically be revealed in public captions, stories, conversations, or published content.$world$,
    $world$Ava lives in a coastal East Coast city.

Public-facing content should normally use broad, non-identifying descriptions such as:

- near the coast
- downtown
- by the water
- at the beach
- near the marsh
- back home
- away in the mountains
- on a weekend trip

Do not reveal Wilmington unless the operator explicitly requests it.$world$,
    $world$Indoor lifestyle content is a normal and important part of Ava’s world.

Believable indoor environments include:

- bedroom
- living room
- kitchen
- bathroom or vanity area
- home office
- porch or enclosed sunroom
- hotel room
- cabin interior
- fireplace area
- coffee shop
- bookstore
- office
- marketing or event venue
- restaurant
- rooftop or indoor social gathering

Ava enjoys taking attractive, feminine, sexy lifestyle images indoors as well as outdoors.

Indoor concepts should feel like believable moments from her life rather than generic studio scenes.

This section defines environments only. Wardrobe and visual presentation remain governed by Lifestyle and Social Creative Direction.$world$,
    $world$Ava’s coastal life may naturally include:

- beaches
- marshes
- docks
- boardwalks
- riverwalks
- coastal parks
- waterfront restaurants
- historic downtown areas
- coffee shops
- bookstores
- local festivals
- farmers markets
- scenic coastal roads
- porches and backyards

Coastal content should remain varied and should not default repeatedly to the same beach or dock setting.$world$,
    $world$Ava grew up with small-town roots and still enjoys returning to a slower, more familiar way of life.

She naturally enjoys weekend trips and getaways involving:

- mountains
- hiking trails
- overlooks
- waterfalls
- lakes
- cabins
- campgrounds
- state parks
- scenic back roads
- mountain towns
- small towns
- local diners
- orchards
- farms
- outdoor festivals

These settings are normal extensions of Ava’s lifestyle and should be considered naturally when generating future concepts.$world$,
    $world$Creator_OS should use Wilmington’s regional seasonal rhythm as the default context for Ava’s home life.

Wardrobe, scenery, activities, lighting, and atmosphere should feel believable for the current month and season.

Do not generate obviously out-of-season content unless the operator explicitly requests it.

A warm coastal winter should not automatically be treated like a snowy northern winter.

Mountain travel may introduce colder temperatures, snow, fireplaces, heavier clothing, or winter activities when believable.

Seasonal context should guide ideas without eliminating indoor content or reasonable travel.$world$,
    $world$Spring may naturally include:

- trails
- gardens
- flowers
- outdoor coffee
- farmers markets
- light layers
- road trips
- coastal walks

Summer may naturally include:

- beaches
- pools
- lakes
- boating
- paddleboarding
- kayaking
- shorts
- crop tops
- swimsuits
- warm evenings
- indoor cooling-off or getting-ready moments

Fall may naturally include:

- hiking
- cabins
- mountain weekends
- scenic drives
- orchards
- pumpkin patches
- fitted sweaters
- leggings
- boots
- bonfires
- cozy indoor content

Winter may naturally include:

- fitted sweaters
- jeans
- leggings
- boots
- coffee shops
- home interiors
- fireplaces
- holiday lights
- cabin trips
- cool coastal walks
- occasional mountain snow$world$,
    $world$Seasonal and holiday concepts may be considered around:

- Valentine’s Day
- spring weekends
- Memorial Day weekend
- July 4th
- late-summer weekends
- Halloween
- Thanksgiving
- Christmas
- New Year’s

Holiday details should be timely, tasteful, and not dominate unrelated content.

Avoid holiday imagery far outside the relevant period unless specifically requested.$world$,
    $world$Ava naturally moves between:

- coastal home life
- work and marketing events
- indoor lifestyle moments
- downtown outings
- beaches and marshes
- hiking and outdoor adventures
- mountain cabins
- lake weekends
- camping trips
- small-town visits
- road trips

Future concept generation should draw from the full range of Ava’s world.

Do not treat her home base as the only place she can appear.

Do not overuse any single setting merely because it has been used successfully before.$world$
FROM public.creator_profiles profile
ON CONFLICT (creator_profile_id) DO NOTHING;
